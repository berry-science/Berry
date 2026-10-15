#!/usr/bin/env python3
"""The claim ledger: findings recorded one at a time, with their evidence.

A ledger is a `claims/` folder in a research repository. Each finding is one
folder in it, named by its id:

    claims/
      README.md                       written by `index`: the list and the graph
      2026-10-10-sta-ramp-com/
        claim.json                    the claim, in Berry Science Library shape
        evidence/01-reasoning.md      each evidence item, as a file
        evidence/02-figure.vl.json
        ...

A claim starts as a draft. `seal` freezes it: the claim and every evidence
file are hashed, and from then on `check` fails if any of it changes. A
sealed claim is never edited; a wrong one is answered by a new claim that
cites it with relation `refutes` (or `extends`, for a refinement).

Citations between claims in the ledger use `"local": "<id>"`. They make the
ledger a graph: `trace` walks it back from one claim to everything it rests
on, which is the record of how the result was reached.

`payload` turns a sealed claim into the arguments of the Library's
`publish_claim` tool, and `published` records the id the Library gave it.

Two more things live in the ledger beside the claims:

    claims/
      conventions.json                the project's conventions, versioned
      sources/arxiv-2502.09437/       reviews of passages of papers the
        2026-10-12-eq-12.json         claims rest on (skill review-source)

A claim names the conventions it is written in as "key@version", and a
citation of a paper names the review of the passage it uses. Both are
covered by the claim's seal: a convention reworded, or a review changed,
after a claim relying on it was sealed fails `check`.

Standard library only; Python 3.9+. Run `claims.py -h` for the commands.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# --- what the Library accepts (2026-10) -----------------------------------------

CLAIM_TYPES = {"result", "method", "negative_result", "calibration"}
EVIDENCE_KINDS = {
    "reasoning",
    "figure",
    "derivation",
    "code",
    "parameters",
    "output",
    "protocol",
    "data",
}
RELATIONS = {"cites", "uses", "extends", "replicates", "refutes"}
EXTERNAL_FORM = re.compile(r"^(doi:10\.\S+|arxiv:\S+|https?://\S+)$")
MAX = {
    "title": 300,
    "statement": 2000,
    "holds_when": 2000,
    "contributors": 16,
    "contributor": 120,
    "anchors": 64,
    "anchor": 255,
    "provenance_bytes": 8000,
    "evidence": 64,
    "content": 16000,
    "caption": 500,
    "format": 32,
    "language": 64,
    "citations": 100,
    "label": 500,
    "reason": 500,
    "external": 500,
}

# Conventions and reviews of papers (the Library's migration 0030).
CONVENTION_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CONVENTION_REF = re.compile(r"^([a-z0-9][a-z0-9._-]*)@(\d+)$")
VERDICTS = {"holds", "holds_with_correction", "fails", "could_not_check"}
READ_FROM = {"latex", "pdf", "html", "other", "none"}
CONVENTION_RELATIONS = {"same", "transform", "conflict", "unrelated"}
MAX.update(
    {
        "convention": 1000,
        "conventions": 32,
        "locator": 200,
        "quote": 2000,
        "purpose": 1000,
        "summary": 4000,
        "method": 500,
        "items": 64,
        "body": 8000,
    }
)
# A paper a claim takes something from, as opposed to code or a web page.
PAPER_FORM = re.compile(r"^(doi:|arxiv:)", re.IGNORECASE)
_ARXIV_URL = re.compile(
    r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"(?P<id>[^?#]+?)(?:v(?P<v>\d+))?(?:\.pdf)?/?(?:[?#].*)?$",
    re.IGNORECASE,
)
_DOI_URL = re.compile(r"^https?://(?:dx\.)?doi\.org/(?P<doi>10\.\S+)$", re.IGNORECASE)

# A model id, as agents' system prompts state them: claude-opus-5-5,
# gpt-5.1, gemini-2.5-pro, o3-mini. A tool version ("SymPy 1.14.0") is not one.
MODEL_ID = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*[-.]\d[a-z0-9.-]*|\b[a-z]+\d+(?:-[a-z0-9]+)+")

STATUSES = {"draft", "sealed"}
ID_FORM = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
# Fields that are the claim itself — what the seal covers. Bookkeeping
# (status, seal, library) is not part of the finding.
CORE_FIELDS = (
    "id",
    "title",
    "statement",
    "claim_type",
    "holds_when",
    "evidence",
    "citations",
    "contributors",
    "anchors",
    "provenance",
)


class LedgerError(Exception):
    """A command that cannot go ahead, said in a sentence."""


# --- finding the ledger -------------------------------------------------------


def git(*args: str, cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def ignored_by_git(paths: list[Path], cwd: Path) -> dict[Path, str]:
    """Which of `paths` git would leave out of a commit, each with the rule
    that does it ("*.txt in .gitignore:3"). Only untracked files are
    reported: one already committed, or added with `git add -f`, is kept.
    Empty outside a git repository."""
    if not paths:
        return {}
    try:
        out = subprocess.run(
            ["git", "check-ignore", "--verbose", "--stdin"],
            cwd=cwd,
            input="\n".join(str(p) for p in paths) + "\n",
            capture_output=True,
            text=True,
        )
    except OSError:
        return {}
    # 0: some are ignored; 1: none are; anything else: not a repository.
    if out.returncode != 0:
        return {}
    found = {}
    for line in out.stdout.splitlines():
        rule, _, path = line.partition("\t")
        source, _, rest = rule.partition(":")
        number, _, pattern = rest.partition(":")
        # --verbose also lists files matched by a negation ("!claims/**"),
        # which is what re-includes them: those are not ignored.
        if pattern.startswith("!"):
            continue
        found[(cwd / path).resolve()] = f"{pattern!r} in {source}:{number}"
    return found


def commit_state(repo: Path, commit: str) -> str:
    """'pushed', 'unpushed' or 'missing'. The two git calls behind it are the
    slowest part of `check` and grow with the history, so a commit once
    found on a remote is remembered — on this machine only, in the git
    directory (`berry-commits.json`), never committed. A pushed commit stays
    pushed; anything else is asked again every time."""
    git_dir = git("rev-parse", "--absolute-git-dir", cwd=repo)
    cache_file = Path(git_dir) / "berry-commits.json" if git_dir else None
    cache: dict[str, str] = {}
    if cache_file and cache_file.is_file():
        try:
            cache = json.loads(cache_file.read_text())
        except (OSError, json.JSONDecodeError):
            cache = {}
    if cache.get(commit) == "pushed":
        return "pushed"
    if git("cat-file", "-e", f"{commit}^{{commit}}", cwd=repo) is None:
        return "missing"
    if not git("branch", "-r", "--contains", commit, cwd=repo):
        return "unpushed"
    if cache_file:
        cache[commit] = "pushed"
        try:
            cache_file.write_text(json.dumps(cache))
        except OSError:
            pass
    return "pushed"


def ledger_root(given: str | None) -> Path:
    """`--root`, else $BERRY_CLAIMS_DIR, else claims/ at the top of the git
    repository the command runs in, else ./claims."""
    if given:
        return Path(given).resolve()
    if os.environ.get("BERRY_CLAIMS_DIR"):
        return Path(os.environ["BERRY_CLAIMS_DIR"]).resolve()
    top = git("rev-parse", "--show-toplevel", cwd=Path.cwd())
    return (Path(top) if top else Path.cwd()) / "claims"


class Ledger:
    def __init__(self, root: Path):
        self.root = root

    def ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name for p in self.root.iterdir() if (p / "claim.json").is_file()
        )

    def path(self, claim_id: str) -> Path:
        return self.root / claim_id

    def load(self, claim_id: str) -> dict[str, Any]:
        file = self.path(claim_id) / "claim.json"
        if not file.is_file():
            raise LedgerError(f"no claim {claim_id!r} in {self.root}")
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{claim_id}/claim.json is not valid JSON: {exc}")

    def save(self, claim: dict[str, Any]) -> None:
        file = self.path(claim["id"]) / "claim.json"
        file.write_text(
            json.dumps(claim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def all(self) -> dict[str, dict[str, Any]]:
        claims = {}
        for claim_id in self.ids():
            try:
                claims[claim_id] = self.load(claim_id)
            except LedgerError:
                claims[claim_id] = {"id": claim_id, "_unreadable": True}
        return claims

    # The project's conventions: claims/conventions.json.

    @property
    def conventions_file(self) -> Path:
        return self.root / "conventions.json"

    def conventions(self) -> dict[str, dict[str, Any]]:
        """key -> {"key", "category", "versions": [{"version", "statement", ...}]}."""
        if not self.conventions_file.is_file():
            return {}
        try:
            data = json.loads(self.conventions_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LedgerError(f"conventions.json is not valid JSON: {exc}")
        return {c.get("key", "?"): c for c in data.get("conventions") or []}

    def save_conventions(self, conventions: dict[str, dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        body = {"conventions": [conventions[k] for k in sorted(conventions)]}
        self.conventions_file.write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def convention(self, ref: str) -> dict[str, Any] | None:
        """The version a "key@version" reference names, or None."""
        m = CONVENTION_REF.match(ref)
        if not m:
            return None
        entry = self.conventions().get(m.group(1))
        for v in (entry or {}).get("versions") or []:
            if v.get("version") == int(m.group(2)):
                return {
                    "key": m.group(1),
                    "category": entry.get("category"),
                    **v,
                }
        return None

    # Reviews of papers: claims/sources/<paper>/<review>.json.

    def source_reviews(self) -> dict[str, dict[str, Any]]:
        """Path relative to the ledger ("sources/arxiv-…/….json") -> review."""
        found: dict[str, dict[str, Any]] = {}
        base = self.root / "sources"
        if not base.is_dir():
            return found
        for file in sorted(base.glob("*/*.json")):
            rel = file.relative_to(self.root).as_posix()
            try:
                found[rel] = json.loads(file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                found[rel] = {"_unreadable": True}
        return found

    def source_review(self, rel: str) -> dict[str, Any] | None:
        file = (self.root / rel).resolve()
        if self.root.resolve() not in file.parents or not file.is_file():
            return None
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"_unreadable": True}

    def save_source_review(self, rel: str, review: dict[str, Any]) -> None:
        (self.root / rel).write_text(
            json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def source_key(external: str) -> tuple[str, str | None]:
    """A paper's key and the version the reference names, as the Library's
    `source_key` computes them: arXiv version dropped, DOI lower-cased, and
    arxiv.org / doi.org links turned into arxiv: / doi: references."""
    value = external.strip()
    m = _ARXIV_URL.match(value)
    if m:
        value = f"arxiv:{m['id']}" + (f"v{m['v']}" if m["v"] else "")
    else:
        m = _DOI_URL.match(value)
        if m:
            value = f"doi:{m['doi']}"
    lowered = value.lower()
    if lowered.startswith("doi:"):
        return "doi:" + lowered[4:], None
    if lowered.startswith("arxiv:"):
        ident = lowered[6:]
        v = re.search(r"v(\d+)$", ident)
        if v:
            return "arxiv:" + ident[: v.start()], f"v{v.group(1)}"
        return "arxiv:" + ident, None
    return value, None


def source_slug(key: str) -> str:
    """The folder a paper's reviews live in: arxiv-2502.09437, doi-10.1103-…"""
    return re.sub(r"[^a-z0-9.]+", "-", key.lower()).strip("-")[:120]


# --- the seal ------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_text(ledger: Ledger, claim: dict[str, Any], item: dict[str, Any]) -> str:
    if "file" in item:
        return (ledger.path(claim["id"]) / item["file"]).read_text(encoding="utf-8")
    return item.get("content") or ""


def review_digest(ledger: Ledger, rel: str) -> str | None:
    """A source review's content, without `library` — publishing it later
    must not break the seal of a claim that cites it."""
    review = ledger.source_review(rel)
    if review is None:
        return None
    review = {k: v for k, v in review.items() if k != "library"}
    return sha256(json.dumps(review, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def seal_of(ledger: Ledger, claim: dict[str, Any]) -> str:
    """One hash over the claim's core fields and the bytes of every evidence
    file, so a change to either breaks it."""
    core = {k: claim.get(k) for k in CORE_FIELDS}
    # What the claim relies on outside its folder, by content: the wording of
    # each convention version it names, and each review of a paper passage
    # it cites. Only added when present, so seals made before conventions
    # and reviews existed still verify.
    if claim.get("conventions"):
        core["conventions"] = [
            [ref, (ledger.convention(ref) or {}).get("statement")]
            for ref in claim["conventions"]
        ]
    reviewed = sorted(
        {c["review"] for c in claim.get("citations") or [] if c.get("review")}
    )
    if reviewed:
        core["_reviews"] = {rel: review_digest(ledger, rel) for rel in reviewed}
    h = hashlib.sha256(
        json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    )
    for item in claim.get("evidence") or []:
        if "file" in item:
            data = (ledger.path(claim["id"]) / item["file"]).read_bytes()
            h.update(item["file"].encode("utf-8") + b"\0" + sha256(data).encode())
    return h.hexdigest()


# --- checking ------------------------------------------------------------------

NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?(?![\w])")


def numbers_in(text: str) -> set[str]:
    """Numbers worth tracing: anything with a decimal point or exponent, and
    integers of two digits or more. Single digits are too often words."""
    found = set()
    for m in NUMBER.finditer(text):
        token = m.group(0).lstrip("+").replace(",", ".")
        if re.fullmatch(r"-?\d", token):
            continue
        found.add(token.lstrip("-"))
    return found


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, claim_id: str, text: str) -> None:
        self.errors.append(f"{claim_id}: {text}")

    def warn(self, claim_id: str, text: str) -> None:
        self.warnings.append(f"{claim_id}: {text}")


def evidence_by_kind(ledger: Ledger, claim: dict[str, Any]) -> list[tuple[str, str]]:
    """(kind, text) of each evidence item that can be read."""
    out = []
    for item in claim.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("content") or ""
        if item.get("file"):
            try:
                text = (ledger.path(claim.get("id", "")) / item["file"]).read_text(
                    encoding="utf-8"
                )
            except (OSError, UnicodeDecodeError):
                text = ""
        out.append((str(item.get("kind") or ""), text))
    return out


# A draft that cites no earlier claim, while earlier claims share this much
# of its title and statement, is asked whether it uses them.
RELATED_MIN_WORDS = 3
RELATED_MIN_SHARE = 0.3


def check_unsaid_dependencies(
    ledger: Ledger, claim: dict[str, Any], claims: dict[str, dict[str, Any]], r: Report
) -> None:
    """Two questions a draft has to answer before it is agreed: does it use
    an earlier claim it does not cite, and where do the numbers in its
    reasoning come from? Both are warnings — the answer can be "it does
    not", said in the reasoning — but they are the questions a batch of
    claims recorded at the end of a phase skips."""
    cid = claim.get("id", "?")
    citations = claim.get("citations") or []
    cited_local = {c["local"] for c in citations if c.get("local")}
    cites_a_claim = bool(cited_local) or any(c.get("claim_id") for c in citations)

    if not cites_a_claim:
        earlier = {
            k: [(f, str(v.get(f) or "")) for f in ("title", "statement", "holds_when")]
            for k, v in claims.items()
            # Made on or before its day; the slug says nothing about order.
            if k != cid and k[:10] <= cid[:10] and not v.get("_unreadable")
        }
        terms = recall_terms(f"{claim.get('title') or ''} {claim.get('statement') or ''}")
        if earlier and terms:
            related = [
                (key, found)
                for _, key, found, _ in recall_rank(earlier, terms)
                if len(found) >= RELATED_MIN_WORDS
                and len(found) / len(terms) >= RELATED_MIN_SHARE
            ][:3]
            if related:
                r.warn(
                    cid,
                    "cites no earlier claim, but these share its subject: "
                    + "; ".join(f"{k} ({len(f)} words in common)" for k, f in related)
                    + ". If it uses one — a value, a result, a setting, a "
                    "conclusion — cite it ('uses', 'extends' or 'refutes'); if "
                    "not, say in the reasoning why it rests on no earlier claim",
                )

    # Numbers the reasoning relies on: from this claim's other evidence, or
    # from a claim it cites. Anything else came from somewhere unsaid.
    items = evidence_by_kind(ledger, claim)
    reasoning = "\n".join(t for k, t in items if k == "reasoning")
    # Dates and claim ids are not values.
    reasoning = re.sub(r"\d{4}-\d{2}-\d{2}", " ", reasoning)
    if not reasoning.strip():
        return
    pool = [t for k, t in items if k != "reasoning"]
    pool += [claim.get("statement") or "", claim.get("holds_when") or ""]
    pool += [f"{c.get('locator') or ''} {c.get('reason') or ''}" for c in citations]
    for other in cited_local:
        if other in claims and not claims[other].get("_unreadable"):
            pool += [t for _, t in recall_texts(ledger, claims[other])]
    text = "\n".join(pool)
    unsourced = sorted(n for n in numbers_in(reasoning) if n not in text)
    if unsourced:
        r.warn(
            cid,
            "numbers in the reasoning found in no other evidence item and no "
            "cited claim: " + ", ".join(unsourced[:12])
            + ". Where does each come from? Attach the output, cite the claim "
            "or paper (with its locator), or state it as an assumption in "
            "holds_when",
        )


def check_claim(
    ledger: Ledger, claim: dict[str, Any], claims: dict[str, dict[str, Any]], r: Report
) -> None:
    cid = claim.get("id", "?")
    folder = ledger.path(cid)
    if claim.get("_unreadable"):
        r.error(cid, "claim.json is not valid JSON")
        return
    if not ID_FORM.match(cid):
        r.error(cid, "the folder name is not an id like 2026-10-10-short-slug")
    status = claim.get("status")
    if status not in STATUSES:
        r.error(cid, f"status is {status!r}; it is 'draft' or 'sealed'")

    # The finding.
    for field in ("title", "statement"):
        value = claim.get(field)
        if not isinstance(value, str) or not value.strip():
            r.error(cid, f"{field} is missing")
        elif len(value) > MAX[field]:
            r.error(cid, f"{field} is {len(value)} characters; at most {MAX[field]}")
    ctype = claim.get("claim_type")
    if ctype is None:
        r.warn(cid, "claim_type is not set (result, method, negative_result, calibration)")
    elif ctype not in CLAIM_TYPES:
        r.error(cid, f"claim_type {ctype!r} is not one of {sorted(CLAIM_TYPES)}")
    holds = claim.get("holds_when")
    if not holds:
        r.warn(cid, "holds_when is empty: under what conditions does it hold?")
    elif len(holds) > MAX["holds_when"]:
        r.error(cid, f"holds_when is {len(holds)} characters; at most {MAX['holds_when']}")

    # Evidence.
    evidence = claim.get("evidence") or []
    if not evidence:
        r.error(cid, "no evidence: a claim is a statement with the evidence behind it")
    elif evidence[0].get("kind") != "reasoning":
        r.warn(cid, "the first evidence item is not 'reasoning' (why the statement follows)")
    if len(evidence) > MAX["evidence"]:
        r.error(cid, f"{len(evidence)} evidence items; at most {MAX['evidence']}")
    text_of_evidence = []
    for n, item in enumerate(evidence, start=1):
        where = f"evidence {n}"
        if item.get("kind") not in EVIDENCE_KINDS:
            r.error(cid, f"{where}: kind {item.get('kind')!r} is not one of {sorted(EVIDENCE_KINDS)}")
        has_file, has_content = "file" in item, "content" in item
        if has_file == has_content:
            r.error(cid, f"{where}: give either 'file' or 'content'")
            continue
        if has_file:
            target = (folder / item["file"]).resolve()
            if folder.resolve() not in target.parents:
                r.error(cid, f"{where}: {item['file']} is outside the claim's folder")
                continue
            if not target.is_file():
                r.error(cid, f"{where}: {item['file']} does not exist")
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                r.error(cid, f"{where}: {item['file']} is not UTF-8 text")
                continue
        else:
            text = item["content"] or ""
        text_of_evidence.append(text)
        if not text.strip():
            r.error(cid, f"{where} is empty")
        if len(text) > MAX["content"] and not item.get("local_only"):
            r.warn(
                cid,
                f"{where} is {len(text)} characters; the Library takes {MAX['content']}. "
                "Mark it \"local_only\": true and add an excerpt as its own item",
            )
        for field in ("caption", "format", "language"):
            if item.get(field) and len(item[field]) > MAX[field]:
                r.error(cid, f"{where}: {field} longer than {MAX[field]}")

    # Every number in the statement should be traceable to the evidence.
    pool = "\n".join(text_of_evidence)
    missing = sorted(
        n for n in numbers_in(claim.get("statement") or "") if n not in pool
    )
    if missing:
        r.warn(
            cid,
            "numbers in the statement found in no evidence item: "
            + ", ".join(missing),
        )

    # What it rests on.
    citations = claim.get("citations") or []
    if not citations:
        r.warn(cid, "no citations: what did this finding build on (data, code, earlier claims)?")
    if len(citations) > MAX["citations"]:
        r.error(cid, f"{len(citations)} citations; at most {MAX['citations']}")
    for n, c in enumerate(citations, start=1):
        where = f"citation [{n}]"
        targets = [k for k in ("local", "claim_id", "external") if c.get(k)]
        if len(targets) != 1:
            r.error(cid, f"{where}: give exactly one of local, claim_id, external")
            continue
        if c.get("relation", "cites") not in RELATIONS:
            r.error(cid, f"{where}: relation {c.get('relation')!r} is not one of {sorted(RELATIONS)}")
        if not c.get("reason"):
            r.warn(cid, f"{where}: no reason — one sentence on what it is used for")
        elif len(c["reason"]) > MAX["reason"]:
            r.error(cid, f"{where}: reason longer than {MAX['reason']}")
        if c.get("local"):
            other = c["local"]
            if other == cid:
                r.error(cid, f"{where}: a claim cannot cite itself")
            elif other not in claims:
                r.error(cid, f"{where}: no claim {other!r} in this ledger")
            elif status == "sealed" and claims[other].get("status") != "sealed":
                r.error(cid, f"{where}: a sealed claim rests on {other}, which is still a draft")
        if c.get("external"):
            if not EXTERNAL_FORM.match(c["external"]):
                r.error(cid, f"{where}: external is doi:10.…, arxiv:… or an http(s) URL")
            elif len(c["external"]) > MAX["external"]:
                r.error(cid, f"{where}: external longer than {MAX['external']}")
        if c.get("locator") and len(c["locator"]) > MAX["locator"]:
            r.error(cid, f"{where}: locator longer than {MAX['locator']}")
        check_cited_passage(ledger, cid, where, c, citations, r)

    # What it may rest on without saying so. Asked of drafts only: a sealed
    # claim cannot change, and the question is for before it is agreed.
    if status == "draft":
        check_unsaid_dependencies(ledger, claim, claims, r)

    # The conventions it is written in.
    refs = claim.get("conventions") or []
    if len(refs) > MAX["conventions"]:
        r.error(cid, f"{len(refs)} conventions; at most {MAX['conventions']}")
    defined = ledger.conventions()
    keys_seen: set[str] = set()
    for ref in refs:
        m = CONVENTION_REF.match(ref) if isinstance(ref, str) else None
        if not m:
            r.error(cid, f"convention {ref!r} is not 'key@version', e.g. 'psd-one-sided@1'")
            continue
        key, version = m.group(1), int(m.group(2))
        if key in keys_seen:
            r.error(cid, f"convention {key} named twice: a claim is written in one version")
        keys_seen.add(key)
        if ledger.convention(ref) is None:
            r.error(
                cid,
                f"convention {ref} is not in conventions.json "
                "(claims.py conv list shows what is defined)",
            )
            continue
        latest = max(v.get("version", 0) for v in defined[key].get("versions") or [])
        if status != "sealed" and version < latest:
            r.warn(cid, f"written in {ref}, but the project now uses {key}@{latest}")
    if defined and not refs and numbers_in(claim.get("statement") or ""):
        r.warn(
            cid,
            "the statement has numbers but names no convention: which of "
            "conventions.json is it written in?",
        )

    # Who and where from.
    contributors = claim.get("contributors") or []
    if len(contributors) > MAX["contributors"] or any(
        len(x) > MAX["contributor"] for x in contributors
    ):
        r.error(cid, "contributors: at most 16, each at most 120 characters")
    agent = (claim.get("provenance") or {}).get("agent") or ""
    if not any(MODEL_ID.search(str(x)) for x in [*contributors, agent]):
        r.warn(
            cid,
            "no contributor names the agent with its model id (as 'claude-…'): "
            "give the exact id your system prompt states, never a guess",
        )
    anchors = claim.get("anchors") or []
    if len(anchors) > MAX["anchors"] or any(len(x) > MAX["anchor"] for x in anchors):
        r.error(cid, "anchors: at most 64, each at most 255 characters")
    provenance = claim.get("provenance") or {}
    if len(json.dumps(provenance).encode()) > MAX["provenance_bytes"]:
        r.error(cid, "provenance is larger than 8 KB")
    commit = provenance.get("commit")
    if not commit and not provenance.get("uncommitted"):
        r.warn(cid, "provenance has no 'commit': which code produced this?")
    elif commit:
        repo = Path(provenance.get("repository_path") or ledger.root.parent)
        state = commit_state(repo, commit)
        if state == "missing":
            r.warn(cid, f"commit {commit[:12]} is not in the git repository at {repo}")
        elif state == "unpushed":
            r.warn(cid, f"commit {commit[:12]} is on no remote branch: push it")

    # Sealed means unchanged.
    if status == "sealed":
        seal = (claim.get("seal") or {}).get("sha256")
        if not seal:
            r.error(cid, "sealed without a seal hash")
        else:
            try:
                now = seal_of(ledger, claim)
            except OSError:
                now = None
            if now != seal:
                r.error(
                    cid,
                    "changed after it was sealed. A sealed claim is not edited: "
                    "restore it (git checkout) and record a new claim that cites it "
                    "with relation 'refutes' or 'extends'",
                )

    # A derivation's executable check, if the formalize-derivation skill is installed.
    check_derivation(ledger, claim, r)


def check_derivation(ledger: Ledger, claim: dict[str, Any], r: Report) -> None:
    """For a claim with a derivation item: the coverage and lint check of the
    formalize-derivation skill, which sits beside this one. Does nothing if
    that skill is not installed."""
    if not any(item.get("kind") == "derivation" for item in claim.get("evidence") or []):
        return
    path = Path(__file__).resolve().parents[2] / "formalize-derivation" / "scripts" / "derivcover.py"
    if not path.is_file():
        return
    cid = claim.get("id", "?")
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("derivcover", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        errors, warnings = module.check_claim(ledger.path(cid), claim)
    except Exception as exc:  # another skill's failure must not stop this check
        r.warn(cid, f"formalize-derivation's check could not run: {exc}")
        return
    for text in errors:
        r.error(cid, text)
    for text in warnings:
        r.warn(cid, text)


def check_cited_passage(
    ledger: Ledger,
    cid: str,
    where: str,
    c: dict[str, Any],
    citations: list[dict[str, Any]],
    r: Report,
) -> None:
    """A paper a claim takes something from: which passage, and whether it
    was checked (skill review-source)."""
    external = c.get("external") or ""
    relation = c.get("relation", "cites")
    if c.get("standard"):
        # A standard reference value (CODATA, NIST, a textbook constant):
        # cited where it is, never reviewed.
        if c.get("review"):
            r.error(cid, f"{where}: a standard reference value has no review; drop one of the two")
        if not c.get("locator"):
            r.warn(cid, f"{where}: a standard reference value — say where (locator: 'CODATA 2018')")
        return
    if c.get("review"):
        if not external:
            r.error(cid, f"{where}: a review belongs to a citation of a paper (external)")
            return
        review = ledger.source_review(c["review"])
        if review is None:
            r.error(cid, f"{where}: no source review {c['review']} in this ledger")
            return
        if review.get("_unreadable"):
            r.error(cid, f"{where}: {c['review']} is not valid JSON")
            return
        if review.get("source") != source_key(external)[0]:
            r.error(
                cid,
                f"{where}: cites {external} but its review is of {review.get('source')}",
            )
        verdict = review.get("verdict")
        if verdict == "fails" and relation in ("uses", "extends", "replicates"):
            r.error(
                cid,
                f"{where}: {relation} a passage its review found wrong "
                f"({c['review']}). Build on a corrected version, or cite it "
                "with 'refutes' or 'cites'",
            )
        elif verdict == "holds_with_correction" and relation == "uses":
            fix = (review.get("correction") or {}).get("local")
            if fix and not any(x.get("local") == fix for x in citations):
                r.warn(
                    cid,
                    f"{where}: the passage is wrong as printed; cite the "
                    f"corrected version, claim {fix}, with 'uses'",
                )
            elif not fix:
                r.warn(
                    cid,
                    f"{where}: the passage is wrong as printed; say in the "
                    "reasoning which corrected form this claim used",
                )
        elif verdict == "could_not_check" and relation == "uses":
            r.warn(
                cid,
                f"{where}: rests on a passage nobody could check; say so in "
                "holds_when as an assumption",
            )
        return
    if relation == "uses" and PAPER_FORM.match(external):
        if not c.get("locator"):
            r.warn(cid, f"{where}: uses {external} — say where (locator: 'Eq. (12)')")
        r.warn(
            cid,
            f"{where}: uses {external} with no source review of that passage "
            "(skill review-source)",
        )


def check_source_review(
    ledger: Ledger,
    rel: str,
    review: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    r: Report,
) -> None:
    if review.get("_unreadable"):
        r.error(rel, "not valid JSON")
        return
    source = review.get("source") or ""
    if not EXTERNAL_FORM.match(source):
        r.error(rel, "source is 'arxiv:…', 'doi:10.…' or an http(s) URL")
    elif source_key(source)[0] != source:
        r.error(rel, f"source is written {source_key(source)[0]!r} (no version, lower case)")
    elif Path(rel).parent.name != source_slug(source):
        r.error(rel, f"lives in the folder of another paper: expected sources/{source_slug(source)}/")
    read_from = review.get("read_from")
    if read_from not in READ_FROM:
        r.error(rel, f"read_from is one of {sorted(READ_FROM)}")
    verdict = review.get("verdict")
    if verdict not in VERDICTS:
        r.error(rel, f"verdict is one of {sorted(VERDICTS)}")
    elif read_from == "none" and verdict != "could_not_check":
        r.error(rel, "read_from 'none': nothing was read, so the verdict is 'could_not_check'")
    summary = review.get("summary") or ""
    if not summary.strip():
        r.error(rel, "summary is missing: what was found, problem first")
    for field in ("summary", "locator", "quote", "purpose", "method"):
        value = review.get(field)
        if value and len(value) > MAX[field]:
            r.error(rel, f"{field} is longer than {MAX[field]}")
    if read_from not in (None, "none") and verdict != "could_not_check":
        if not review.get("quote"):
            r.warn(rel, "no quote: give the passage verbatim, so a reader finds it")
        if not review.get("locator"):
            r.warn(rel, "no locator: which equation, table or section was checked?")
    if not review.get("purpose"):
        r.warn(rel, "no purpose: what is the passage used for?")
    for n, conv in enumerate(review.get("conventions") or [], start=1):
        if not (conv.get("paper") or "").strip():
            r.error(rel, f"convention {n}: 'paper' (the paper's convention) is missing")
        rel_ = conv.get("relation")
        if rel_ is not None and rel_ not in CONVENTION_RELATIONS:
            r.error(rel, f"convention {n}: relation is one of {sorted(CONVENTION_RELATIONS)}")
        if rel_ == "transform" and not conv.get("transform"):
            r.error(rel, f"convention {n}: relation 'transform' needs the transform")
        maps_to = conv.get("maps_to")
        if maps_to and ledger.convention(maps_to) is None:
            r.warn(rel, f"convention {n}: maps_to {maps_to} is not in conventions.json")
    items = review.get("items") or []
    if len(items) > MAX["items"]:
        r.error(rel, f"{len(items)} items; at most {MAX['items']}")
    for n, item in enumerate(items, start=1):
        if not (item.get("body") or "").strip():
            r.error(rel, f"item {n}: body is missing")
    fix = (review.get("correction") or {}).get("local")
    if fix and fix not in claims:
        r.error(rel, f"correction names claim {fix}, which is not in this ledger")
    if verdict == "holds_with_correction" and not fix and not any(
        i.get("proposed_fix") for i in items
    ):
        r.warn(rel, "holds_with_correction without the corrected version: give a proposed_fix")


def cycles(claims: dict[str, dict[str, Any]]) -> list[list[str]]:
    found, state, stack = [], {}, []

    def visit(cid: str) -> None:
        state[cid] = 1
        stack.append(cid)
        for c in claims.get(cid, {}).get("citations") or []:
            other = c.get("local")
            if other not in claims:
                continue
            if state.get(other) == 1:
                found.append(stack[stack.index(other) :] + [other])
            elif other not in state:
                visit(other)
        stack.pop()
        state[cid] = 2

    for cid in claims:
        if cid not in state:
            visit(cid)
    return found


def claim_files(ledger: Ledger, claim: dict[str, Any]) -> list[Path]:
    """The files that make up a claim: claim.json and its evidence files."""
    folder = ledger.path(claim["id"])
    files = [folder / "claim.json"]
    for item in claim.get("evidence") or []:
        if "file" in item and (folder / item["file"]).is_file():
            files.append(folder / item["file"])
    # What it relies on outside its folder must be committed too.
    for c in claim.get("citations") or []:
        if c.get("review") and (ledger.root / c["review"]).is_file():
            files.append(ledger.root / c["review"])
    if claim.get("conventions") and ledger.conventions_file.is_file():
        files.append(ledger.conventions_file)
    return [f.resolve() for f in files]


def check_ignored(
    ledger: Ledger, chosen: list[dict[str, Any]], r: Report
) -> None:
    """A claim file that git ignores is never committed: the record would
    look complete here and be missing for everyone else. An error, so it
    cannot be sealed that way."""
    if not ledger.root.is_dir():
        return
    owner = {f: c["id"] for c in chosen for f in claim_files(ledger, c)}
    hits = ignored_by_git(list(owner), ledger.root)
    rel = ledger.root.name
    for path, rule in sorted(hits.items()):
        cid = owner.get(path)
        if cid is None:
            continue
        folder = ledger.path(cid).resolve()
        name = (
            path.relative_to(folder)
            if folder in path.parents
            else path.relative_to(ledger.root.resolve())
        )
        r.error(
            cid,
            f"{name} is ignored by git ({rule}), so it would never be "
            f"committed. Add the line `!{rel}/**` to that .gitignore, after "
            "the rule (or commit the file with `git add -f`)",
        )


def check_conventions(ledger: Ledger, r: Report) -> None:
    where = "conventions.json"
    try:
        defined = ledger.conventions()
    except LedgerError as exc:
        r.error(where, str(exc))
        return
    for key, entry in defined.items():
        if not CONVENTION_KEY.match(key or ""):
            r.error(where, f"key {key!r}: lower-case letters, digits, '.', '_', '-'")
        versions = [v.get("version") for v in entry.get("versions") or []]
        if versions != list(range(1, len(versions) + 1)):
            r.error(where, f"{key}: versions are 1, 2, 3, … in order; found {versions}")
        for v in entry.get("versions") or []:
            text = v.get("statement") or ""
            if not text.strip():
                r.error(where, f"{key}@{v.get('version')}: statement is missing")
            elif len(text) > MAX["convention"]:
                r.error(where, f"{key}@{v.get('version')}: longer than {MAX['convention']}")


def check(ledger: Ledger, only: list[str] | None = None) -> Report:
    claims = ledger.all()
    r = Report()
    chosen = []
    for cid in only or claims:
        if cid.startswith("sources/"):
            review = ledger.source_review(cid)
            if review is None:
                r.error(cid, f"no such source review in {ledger.root}")
            else:
                check_source_review(ledger, cid, review, claims, r)
            continue
        if cid not in claims:
            r.error(cid, f"no such claim in {ledger.root}")
            continue
        check_claim(ledger, claims[cid], claims, r)
        if not claims[cid].get("_unreadable"):
            chosen.append(claims[cid])
    if not only:
        check_conventions(ledger, r)
        for rel, review in ledger.source_reviews().items():
            check_source_review(ledger, rel, review, claims, r)
    check_ignored(ledger, chosen, r)
    for loop in cycles(claims):
        r.error(loop[0], "citations go in a circle: " + " -> ".join(loop))
    return r


# --- commands ---------------------------------------------------------------------


def slugify(text: str, words: int = 5) -> str:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(parts[:words]) or "claim"


def finding_date(given: str | None) -> str:
    """The date in a claim's id: when the finding was made, which is today
    unless it is being recorded after the fact."""
    if given is None:
        return dt.date.today().isoformat()
    try:
        day = dt.date.fromisoformat(given)
    except ValueError:
        raise LedgerError(f"--date {given!r} is not a date like 2026-10-08")
    if day > dt.date.today():
        raise LedgerError(f"--date {given} is in the future")
    return day.isoformat()


def cmd_new(ledger: Ledger, a: argparse.Namespace) -> int:
    day = finding_date(a.date)
    base = f"{day}-{slugify(a.slug or a.title)}"
    cid, n = base, 2
    while ledger.path(cid).exists():
        cid, n = f"{base}-{n}", n + 1
    folder = ledger.path(cid)
    (folder / "evidence").mkdir(parents=True)
    claim = {
        "id": cid,
        "status": "draft",
        "title": a.title,
        "statement": "",
        "claim_type": a.type,
        "holds_when": "",
        "evidence": [
            {"kind": "reasoning", "file": "evidence/01-reasoning.md", "format": "markdown"}
        ],
        "citations": [],
        "conventions": [],
        "contributors": [],
        "anchors": [],
        "provenance": {},
        "library": None,
    }
    (folder / "evidence" / "01-reasoning.md").write_text("", encoding="utf-8")
    ledger.save(claim)
    print(cid)
    print(folder)
    return 0


def print_report(r: Report) -> None:
    for line in r.errors:
        print(f"ERROR   {line}")
    for line in r.warnings:
        print(f"warning {line}")
    print(f"{len(r.errors)} error(s), {len(r.warnings)} warning(s)")


def cmd_check(ledger: Ledger, a: argparse.Namespace) -> int:
    if not ledger.ids() and not ledger.source_reviews() and not ledger.conventions_file.is_file():
        print(f"no claims in {ledger.root}")
        return 0
    r = check(ledger, a.ids or None)
    print_report(r)
    return 1 if r.errors else 0


def cmd_seal(ledger: Ledger, a: argparse.Namespace) -> int:
    claim = ledger.load(a.id)
    if claim.get("status") == "sealed":
        raise LedgerError(f"{a.id} is already sealed")
    claim["status"] = "sealed"  # checked as it will be once sealed
    claim["seal"] = {"sha256": seal_of(ledger, claim)}
    # Checked in memory, as it will be once sealed; disk still has the draft.
    r = Report()
    check_claim(ledger, claim, {**ledger.all(), a.id: claim}, r)
    check_ignored(ledger, [claim], r)
    if r.errors:
        print_report(r)
        print(f"not sealed: fix the errors in {a.id} first")
        return 1
    claim["seal"]["at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    ledger.save(claim)
    print_report(r)
    print(f"sealed {a.id}")
    return 0


def label(claim: dict[str, Any]) -> str:
    kind = claim.get("claim_type") or "claim"
    status = claim.get("status", "?")
    lib = " · in the Library" if (claim.get("library") or {}).get("id") else ""
    return f"[{kind}, {status}{lib}] {claim.get('title', '')}"


def cmd_trace(ledger: Ledger, a: argparse.Namespace) -> int:
    claims = ledger.all()
    if a.id not in claims:
        raise LedgerError(f"no claim {a.id!r} in {ledger.root}")
    seen: set[str] = set()

    def walk(cid: str, prefix: str) -> None:
        cits = claims[cid].get("citations") or []
        for i, c in enumerate(cits):
            last = i == len(cits) - 1
            branch, more = ("└─ ", "   ") if last else ("├─ ", "│  ")
            rel = c.get("relation", "cites")
            if c.get("local"):
                other = c["local"]
                known = claims.get(other)
                text = f"{other}  {label(known)}" if known else f"{other}  (missing)"
                again = "  (above)" if other in seen else ""
                print(f"{prefix}{branch}{rel} {text}{again}")
                if known and other not in seen:
                    seen.add(other)
                    walk(other, prefix + more)
            else:
                target = c.get("claim_id") or c.get("external")
                if c.get("locator"):
                    target = f"{target}, {c['locator']}"
                if c.get("review"):
                    review = ledger.source_review(c["review"]) or {}
                    target = f"{target} [reviewed: {review.get('verdict') or '?'}]"
                note = f" — {c['reason']}" if c.get("reason") else ""
                print(f"{prefix}{branch}{rel} {target}{note}")

    print(f"{a.id}  {label(claims[a.id])}")
    seen.add(a.id)
    walk(a.id, "")
    return 0


def cmd_index(ledger: Ledger, a: argparse.Namespace) -> int:
    claims = {k: v for k, v in ledger.all().items() if not v.get("_unreadable")}
    lines = [
        "# Claims",
        "",
        "One folder per finding: `claim.json` and its evidence files. Sealed",
        "claims are never edited; a wrong one is answered by a newer claim that",
        "cites it. Written by `claims.py index` — do not edit by hand.",
        "",
        "| Claim | Type | Status | Audit | Title | Library |",
        "|---|---|---|---|---|---|",
    ]
    for cid, c in sorted(claims.items(), reverse=True):
        lib = c.get("library") or {}
        link = f"[{lib['id'][:8]}]({lib['url']})" if lib.get("url") else ""
        title = (c.get("title") or "").replace("|", "\\|")
        state, _ = audit_state(ledger, claims, cid)
        audit = {"current": "[current](audits/" + cid + ".json)",
                 "stale": "[stale](audits/" + cid + ".json)",
                 "never": "—", "draft": ""}[state]
        lines.append(
            f"| [{cid}]({cid}/claim.json) | {c.get('claim_type') or ''} | "
            f"{c.get('status', '')} | {audit} | {title} | {link} |"
        )
    edges = [
        (cid, cit.get("local"), cit.get("relation", "cites"))
        for cid, c in claims.items()
        for cit in c.get("citations") or []
        if cit.get("local") in claims
    ]
    if edges:
        node = {cid: f"c{i}" for i, cid in enumerate(sorted(claims))}
        lines += ["", "## How they build on each other", "", "```mermaid", "graph BT"]
        for cid in sorted(claims):
            title = (claims[cid].get("title") or cid)[:60].replace('"', "'")
            lines.append(f'  {node[cid]}["{cid}<br/>{title}"]')
        for src, dst, rel in edges:
            lines.append(f"  {node[src]} -- {rel} --> {node[dst]}")
        lines.append("```")
    defined = ledger.conventions()
    if defined:
        lines += [
            "",
            "## Conventions",
            "",
            "What the claims' numbers are written in (`conventions.json`). A",
            "changed convention is a new version; old claims keep theirs.",
            "",
            "| Convention | Statement |",
            "|---|---|",
        ]
        for key in sorted(defined):
            v = latest(defined[key])
            text = (v.get("statement") or "").replace("|", "\\|")
            lines.append(f"| `{key}@{v.get('version')}` | {text} |")
    reviews = ledger.source_reviews()
    if reviews:
        lines += [
            "",
            "## Papers checked",
            "",
            "Passages of papers the claims rest on, each checked before use",
            "(`sources/`).",
            "",
            "| Paper | Passage | Verdict | Review |",
            "|---|---|---|---|",
        ]
        for rel, review in reviews.items():
            lines.append(
                f"| {review.get('source', '')} | {review.get('locator') or 'whole paper'} "
                f"| {review.get('verdict') or ''} | [{Path(rel).name}]({rel}) |"
            )
    out = ledger.root / "README.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    r = Report()
    check_ignored(ledger, list(claims.values()), r)
    for line in r.errors:
        print(f"warning {line}", file=sys.stderr)
    return 0


def publish_order(
    claims: dict[str, dict[str, Any]], target: str, ledger: Ledger | None = None
) -> list[str]:
    """`target` and everything it rests on that the Library does not have
    yet, in the order to publish it: cited claims first, and before a claim,
    the source reviews it cites (as "sources/…" paths) — each after the
    correction claim it names."""
    order: list[str] = []
    visiting: set[str] = set()
    reviews = ledger.source_reviews() if ledger else {}

    def visit_review(rel: str) -> None:
        review = reviews.get(rel)
        if rel in order or rel in visiting or review is None:
            return
        if (review.get("library") or {}).get("id"):
            return
        visiting.add(rel)
        fix = (review.get("correction") or {}).get("local")
        if fix in claims:
            visit(fix)
        order.append(rel)

    def visit(cid: str) -> None:
        if cid in order or cid in visiting or (claims[cid].get("library") or {}).get("id"):
            return
        visiting.add(cid)
        for c in claims[cid].get("citations") or []:
            if c.get("local") in claims:
                visit(c["local"])
            if c.get("review"):
                visit_review(c["review"])
        order.append(cid)

    if target.startswith("sources/"):
        visit_review(target)
    else:
        visit(target)
    return order


def cmd_order(ledger: Ledger, a: argparse.Namespace) -> int:
    claims = ledger.all()
    if a.id not in claims and ledger.source_review(a.id) is None:
        raise LedgerError(f"no claim {a.id!r} in {ledger.root}")
    for cid in publish_order(claims, a.id, ledger):
        print(cid)
    return 0


def cmd_payload(ledger: Ledger, a: argparse.Namespace) -> int:
    claims = ledger.all()
    claim = claims.get(a.id)
    if claim is None:
        raise LedgerError(f"no claim {a.id!r} in {ledger.root}")
    if claim.get("status") != "sealed":
        raise LedgerError(f"{a.id} is a draft: seal it before publishing")
    r = check(ledger, [a.id])
    if r.errors:
        print_report(r)
        raise LedgerError(f"{a.id} does not pass check")
    if (claim.get("library") or {}).get("id"):
        raise LedgerError(f"{a.id} is already in the Library: {claim['library']['id']}")

    evidence = []
    for n, item in enumerate(claim["evidence"], start=1):
        if item.get("local_only"):
            continue  # kept in the ledger in full; an excerpt item stands in
        text = evidence_text(ledger, claim, item)
        if len(text) > MAX["content"]:
            raise LedgerError(
                f"evidence {n} is {len(text)} characters; the Library takes "
                f"{MAX['content']}. It cannot be marked local_only now that the "
                "claim is sealed: record a new claim that extends this one, with "
                "the full file local_only and an excerpt beside it"
            )
        out = {"kind": item["kind"], "content": text}
        for field in ("format", "language", "caption"):
            if item.get(field):
                out[field] = item[field]
        evidence.append(out)

    order = " ".join(publish_order(claims, a.id, ledger))
    citations = []
    for n, c in enumerate(claim.get("citations") or [], start=1):
        out = {k: c[k] for k in ("relation", "reason", "label", "locator") if c.get(k)}
        if c.get("local"):
            lib = (claims[c["local"]].get("library") or {}).get("id")
            if not lib:
                raise LedgerError(
                    f"citation [{n}] is {c['local']}, which is not in the Library yet. "
                    f"Publish in this order: {order}"
                )
            out["claim_id"] = lib
        elif c.get("claim_id"):
            out["claim_id"] = c["claim_id"]
        else:
            out["external"] = c["external"]
        if c.get("review"):
            review = ledger.source_review(c["review"]) or {}
            rid = (review.get("library") or {}).get("id")
            if not rid:
                raise LedgerError(
                    f"citation [{n}] names the source review {c['review']}, which "
                    f"is not in the Library yet. Publish in this order: {order}"
                )
            out["source_review_id"] = rid
        citations.append(out)

    conventions = []
    for ref in claim.get("conventions") or []:
        conv = ledger.convention(ref)
        if conv is None:
            raise LedgerError(f"convention {ref} is not in conventions.json")
        entry = {"key": conv["key"], "version": conv["version"], "statement": conv["statement"]}
        if conv.get("category"):
            entry["category"] = conv["category"]
        conventions.append(entry)

    provenance = dict(claim.get("provenance") or {})
    provenance.pop("repository_path", None)  # a path on this machine
    provenance["ledger_id"] = a.id
    provenance["ledger_seal"] = claim["seal"]["sha256"]
    anchors = list(claim.get("anchors") or [])
    if f"ledger:{a.id}" not in anchors:
        anchors.append(f"ledger:{a.id}")

    payload: dict[str, Any] = {
        "title": claim["title"],
        "statement": claim["statement"],
        "evidence": evidence,
        "citations": citations,
        "contributors": claim.get("contributors") or [],
        "anchors": anchors[: MAX["anchors"]],
        "provenance": provenance,
    }
    for field in ("claim_type", "holds_when"):
        if claim.get(field):
            payload[field] = claim[field]
    if conventions:
        payload["conventions"] = conventions
    if a.space_id:
        payload["space_id"] = a.space_id
    elif not a.public:
        payload["private"] = True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_published(ledger: Ledger, a: argparse.Namespace) -> int:
    claim = ledger.load(a.id)
    if claim.get("status") != "sealed":
        raise LedgerError(f"{a.id} is a draft; only a sealed claim is published")
    if not re.fullmatch(r"[0-9a-f-]{36}", a.library_id):
        raise LedgerError(f"{a.library_id!r} is not a Library claim id")
    claim["library"] = {
        "id": a.library_id,
        "url": f"https://berry.science/library/{a.library_id}",
        "visibility": a.visibility,
        "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    ledger.save(claim)  # `library` is bookkeeping, outside the seal
    print(f"{a.id} -> {claim['library']['url']}")
    return 0


# --- conventions ------------------------------------------------------------------


def latest(entry: dict[str, Any]) -> dict[str, Any]:
    return max(entry.get("versions") or [{}], key=lambda v: v.get("version", 0))


def cmd_conv_list(ledger: Ledger, a: argparse.Namespace) -> int:
    defined = ledger.conventions()
    if not defined:
        print(f"no conventions in {ledger.conventions_file}")
        return 0
    for key in sorted(defined):
        v = latest(defined[key])
        cat = f" [{defined[key]['category']}]" if defined[key].get("category") else ""
        print(f"{key}@{v.get('version')}{cat}  {v.get('statement')}")
    return 0


def cmd_conv_add(ledger: Ledger, a: argparse.Namespace) -> int:
    if not CONVENTION_KEY.match(a.key):
        raise LedgerError(f"{a.key!r}: a key is lower-case letters, digits, '.', '_', '-'")
    defined = ledger.conventions()
    if a.key in defined:
        raise LedgerError(
            f"{a.key} exists; a changed convention is a new version: "
            f"claims.py conv revise {a.key} \"…\" --why \"…\""
        )
    entry: dict[str, Any] = {"key": a.key, "versions": []}
    if a.category:
        entry["category"] = a.category
    entry["versions"].append(
        {"version": 1, "statement": a.statement, "since": dt.date.today().isoformat()}
    )
    defined[a.key] = entry
    ledger.save_conventions(defined)
    print(f"{a.key}@1")
    return 0


def cmd_conv_revise(ledger: Ledger, a: argparse.Namespace) -> int:
    defined = ledger.conventions()
    if a.key not in defined:
        raise LedgerError(f"no convention {a.key}; add it with claims.py conv add")
    version = latest(defined[a.key]).get("version", 0) + 1
    defined[a.key]["versions"].append(
        {
            "version": version,
            "statement": a.statement,
            "since": dt.date.today().isoformat(),
            "why": a.why,
        }
    )
    ledger.save_conventions(defined)
    print(f"{a.key}@{version}")
    return 0


def cmd_conv_show(ledger: Ledger, a: argparse.Namespace) -> int:
    entry = ledger.conventions().get(a.key)
    if entry is None:
        raise LedgerError(f"no convention {a.key}")
    claims = ledger.all()
    for v in entry.get("versions") or []:
        ref = f"{a.key}@{v.get('version')}"
        users = sorted(cid for cid, c in claims.items() if ref in (c.get("conventions") or []))
        why = f"  (why: {v['why']})" if v.get("why") else ""
        print(f"{ref}  since {v.get('since', '?')}{why}\n  {v.get('statement')}")
        for cid in users:
            print(f"  used by {cid}")
    return 0


# --- reviews of papers ----------------------------------------------------------------


def cmd_source_new(ledger: Ledger, a: argparse.Namespace) -> int:
    key, version = source_key(a.source)
    if not EXTERNAL_FORM.match(key):
        raise LedgerError(f"{a.source!r} is not 'arxiv:…', 'doi:10.…' or a URL")
    day = finding_date(a.date)
    folder = ledger.root / "sources" / source_slug(key)
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{day}-{slugify(a.slug or a.locator or 'whole-paper', 4)}"
    name, n = base, 2
    while (folder / f"{name}.json").exists():
        name, n = f"{base}-{n}", n + 1
    rel = f"sources/{source_slug(key)}/{name}.json"
    ledger.save_source_review(
        rel,
        {
            "source": key,
            "source_version": version,
            "locator": a.locator,
            "quote": "",
            "purpose": "",
            "read_from": "",
            "verdict": "",
            "summary": "",
            "method": "",
            "conventions": [],
            "items": [],
            "correction": None,
            "reviewer": {"agent": None, "human": None},
            "date": day,
            "library": None,
        },
    )
    print(rel)
    return 0


def cmd_source_list(ledger: Ledger, a: argparse.Namespace) -> int:
    key = source_key(a.source)[0] if a.source else None
    reviews = ledger.source_reviews()
    shown = 0
    for rel, review in reviews.items():
        if key and review.get("source") != key:
            continue
        lib = " · in the Library" if (review.get("library") or {}).get("id") else ""
        print(
            f"{rel}  {review.get('verdict') or '?'}  "
            f"{review.get('locator') or 'whole paper'}{lib}"
        )
        shown += 1
    if not shown:
        print("no source reviews" + (f" of {key}" if key else ""))
    return 0


def cmd_source_payload(ledger: Ledger, a: argparse.Namespace) -> int:
    review = ledger.source_review(a.path)
    if review is None:
        raise LedgerError(f"no source review {a.path} in {ledger.root}")
    claims = ledger.all()
    r = Report()
    check_source_review(ledger, a.path, review, claims, r)
    if r.errors:
        print_report(r)
        raise LedgerError(f"{a.path} does not pass check")
    if (review.get("library") or {}).get("id"):
        raise LedgerError(f"{a.path} is already in the Library: {review['library']['id']}")
    payload: dict[str, Any] = {
        "source": review["source"],
        "read_from": review["read_from"],
        "verdict": review["verdict"],
        "summary": review["summary"],
    }
    for field in ("source_version", "locator", "quote", "purpose"):
        if review.get(field):
            payload[field] = review[field]
    reviewer = review.get("reviewer") or {}
    method = review.get("method") or ""
    if reviewer.get("agent") and reviewer["agent"] not in method:
        method = f"{method} ({reviewer['agent']})".strip() if method else reviewer["agent"]
    if method:
        payload["method"] = method[: MAX["method"]]
    if review.get("conventions"):
        payload["conventions"] = review["conventions"]
    if review.get("items"):
        payload["items"] = [
            {
                k: item[k]
                for k in (
                    "quote", "body", "severity", "error_classes",
                    "proposed_fix", "proposed_fix_format",
                )
                if item.get(k)
            }
            for item in review["items"]
        ]
    fix = (review.get("correction") or {}).get("local")
    if fix:
        lib = (claims[fix].get("library") or {}).get("id")
        if not lib:
            raise LedgerError(
                f"the correction {fix} is not in the Library yet. Publish in this "
                f"order: {' '.join(publish_order(claims, a.path, ledger))}"
            )
        payload["correction_claim_id"] = lib
    if a.space_id:
        payload["space_id"] = a.space_id
    elif not a.public:
        payload["private"] = True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_source_published(ledger: Ledger, a: argparse.Namespace) -> int:
    review = ledger.source_review(a.path)
    if review is None:
        raise LedgerError(f"no source review {a.path} in {ledger.root}")
    if not re.fullmatch(r"[0-9a-f-]{36}", a.library_id):
        raise LedgerError(f"{a.library_id!r} is not a Library id")
    from urllib.parse import quote_plus

    review["library"] = {
        "id": a.library_id,
        "url": "https://berry.science/library/source?key=" + quote_plus(review["source"]),
        "visibility": a.visibility,
        "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    ledger.save_source_review(a.path, review)
    print(f"{a.path} -> {review['library']['url']}")
    return 0


# --- recall: what the ledger already says -------------------------------------------------
#
# Keyword search, not meaning: the Library's `search` (berry.science) ranks
# by meaning too. Here a claim ranks by how many of the query's words it
# carries, and where — title and statement count more than evidence — with
# rarer words counting more. Words match by their start ("oscillat" finds
# "oscillation"), so a plural or another ending is still found.

RECALL_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for",
    "from", "has", "have", "how", "if", "in", "into", "is", "it", "its", "of",
    "on", "or", "than", "that", "the", "this", "to", "was", "we", "were",
    "what", "when", "where", "which", "with", "whether", "already", "checked",
}
RECALL_WORD = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|[^\W\d_]\w*", re.UNICODE)
# Where a word was found, and how much that counts.
RECALL_WEIGHT = {
    "title": 3.0, "statement": 2.0, "holds_when": 2.0, "anchors": 2.0,
    "caption": 1.0, "evidence": 1.0, "source": 2.0,
}
RECALL_MAX_FILE = 2_000_000


def recall_terms(query: str) -> list[str]:
    """The query's words, lowercase, without the small ones. A word is cut
    to its first six letters (at least), so endings do not matter."""
    terms = []
    for w in RECALL_WORD.findall(query.lower()):
        if w in RECALL_STOP or (len(w) < 2 and not w[0].isdigit()):
            continue
        # A number matches with either sign: "-5.5" is found in "→ -5.5".
        stem = w.lstrip("+-") if w[0] in "+-" or w[0].isdigit() else w[: max(6, len(w) - 3)]
        if stem not in terms:
            terms.append(stem)
    return terms


def recall_texts(ledger: Ledger, claim: dict[str, Any]) -> list[tuple[str, str]]:
    """(where, text) for everything a claim says: its fields, then each
    evidence item, local-only ones included — they are on this machine."""
    texts = [(f, str(claim.get(f) or "")) for f in ("title", "statement", "holds_when")]
    texts.append(("anchors", " ".join(claim.get("anchors") or [])))
    folder = ledger.path(claim.get("id", ""))
    for item in claim.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        if item.get("caption"):
            texts.append(("caption", item["caption"]))
        body = item.get("content") or ""
        if item.get("file"):
            file = folder / item["file"]
            try:
                if file.is_file() and file.stat().st_size <= RECALL_MAX_FILE:
                    body = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                body = ""
        if body:
            texts.append((f"evidence {item.get('file') or item.get('kind', '')}", body))
    return texts


def review_texts(review: dict[str, Any]) -> list[tuple[str, str]]:
    head = " ".join(str(review.get(f) or "") for f in ("source", "locator", "purpose"))
    texts = [("source", head)]
    for f in ("quote", "summary"):
        if review.get(f):
            texts.append((f, str(review[f])))
    for item in review.get("items") or []:
        if isinstance(item, dict) and item.get("body"):
            texts.append(("items", str(item["body"])))
    return texts


def _weight(where: str) -> float:
    return RECALL_WEIGHT.get(where.split(" ")[0], 1.0)


def _hits_in(text: str, term: str) -> list[str]:
    """The lines of text holding a word that starts with term."""
    if term[0].isdigit():
        pattern = re.compile(r"(?<![\d.])" + re.escape(term) + r"(?![\d])")
    else:
        pattern = re.compile(r"(?<!\w)" + re.escape(term), re.IGNORECASE)
    return [ln.strip() for ln in text.splitlines() if pattern.search(ln)]


def recall_rank(
    entries: dict[str, list[tuple[str, str]]], terms: list[str]
) -> list[tuple[float, str, list[str], list[tuple[str, str]]]]:
    """(score, key, terms found, [(where, line)]) for every entry carrying at
    least one term, best first. A term's weight is rarer = more (idf)."""
    import math

    n = max(len(entries), 1)
    found: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for key, texts in entries.items():
        for term in terms:
            for where, text in texts:
                for line in _hits_in(text, term):
                    found.setdefault(key, {}).setdefault(term, []).append((where, line))
    df = {t: sum(1 for k in found if t in found[k]) for t in terms}
    ranked = []
    for key, by_term in found.items():
        score = 0.0
        for term, places in by_term.items():
            idf = math.log(1 + n / df[term])
            best = max(_weight(w) for w, _ in places)
            score += idf * (best + 0.1 * min(len(places) - 1, 5))
        # A claim carrying more of the query's words beats one repeating one.
        score *= len(by_term) / len(terms)
        lines: list[tuple[str, str]] = []
        for places in by_term.values():
            for where, line in sorted(places, key=lambda p: -_weight(p[0])):
                if (where, line) not in lines:
                    lines.append((where, line))
                break
        ranked.append((score, key, list(by_term), lines))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return ranked


def _snippet(line: str, width: int = 150) -> str:
    line = re.sub(r"\s+", " ", line)
    return line if len(line) <= width else line[: width - 1] + "…"


def claim_titles(ledger: Ledger) -> list[str]:
    """Every claim, newest first: id, kind and state, title."""
    claims = ledger.all()
    lines = []
    for cid in sorted(claims, reverse=True):
        c = claims[cid]
        if c.get("_unreadable"):
            lines.append(f"{cid}  [unreadable claim.json]")
        else:
            lines.append(f"{cid}  {label(c)}")
    return lines


def cmd_recall(ledger: Ledger, a: argparse.Namespace) -> int:
    if a.titles:
        lines = claim_titles(ledger)
        print("\n".join(lines) if lines else f"no claims in {ledger.root}")
        return 0
    query = " ".join(a.query).strip()
    if not query:
        raise LedgerError("give what to look for, or --titles for the list")
    claims = {k: v for k, v in ledger.all().items() if not v.get("_unreadable")}
    entries = {cid: recall_texts(ledger, c) for cid, c in claims.items()}
    for rel, review in ledger.source_reviews().items():
        if not review.get("_unreadable"):
            entries[rel] = review_texts(review)

    if a.exact:
        # Unranked and complete: every entry with the string, every line.
        needle = query.lower()
        if len(needle) < 3:
            raise LedgerError("--exact needs at least three characters")
        shown = 0
        for key in sorted(entries):
            places = [
                (where, ln.strip())
                for where, text in entries[key]
                for ln in text.splitlines()
                if needle in ln.lower()
            ]
            if not places:
                continue
            shown += 1
            head = label(claims[key]) if key in claims else "[source review]"
            print(f"{key}  {head}")
            for where, line in places[: a.lines]:
                print(f"    {where}: {_snippet(line)}")
            if len(places) > a.lines:
                print(f"    … {len(places) - a.lines} more line(s)")
        if not shown:
            print(f"nothing in the ledger contains {query!r}")
        return 0

    terms = recall_terms(query)
    if not terms:
        raise LedgerError(f"no words to look for in {query!r}")
    ranked = recall_rank(entries, terms)
    if not ranked:
        print(f"no claim or source review carries any of: {', '.join(terms)}")
        return 0
    for score, key, found, lines in ranked[: a.limit]:
        head = label(claims[key]) if key in claims else "[source review]"
        print(f"{key}  {head}")
        print(f"    words found: {len(found)} of {len(terms)} ({', '.join(found)})")
        for where, line in lines[: a.lines]:
            print(f"    {where}: {_snippet(line)}")
    if len(ranked) > a.limit:
        print(f"… {len(ranked) - a.limit} more with fewer of the words (--limit)")
    return 0


# --- drafts waiting for the researcher ---------------------------------------------------


def cmd_pending(ledger: Ledger, a: argparse.Namespace) -> int:
    """Drafts not yet sealed, oldest first, each with what check says."""
    claims = ledger.all()
    drafts = sorted(cid for cid, c in claims.items() if c.get("status") == "draft")
    if not drafts:
        print("no drafts")
        return 0
    for cid in drafts:
        r = Report()
        check_claim(ledger, claims[cid], claims, r)
        state = f"{len(r.errors)} error(s)" if r.errors else "passes check"
        print(f"{cid}  [{state}, {len(r.warnings)} warning(s)]  {claims[cid].get('title', '')}")
    return 0


# --- audits: what check-claims found, and when it has to look again --------------------
#
# A sealed claim cannot change, so a judgment of it stays true — as long as
# what it rests on stays the same. An audit records the claim's seal and
# everything below it at the time: the seals of every ledger claim in its
# chain, the content of every review of a paper the chain cites, which
# claims refuted any of them, and which reviews of those papers existed. It
# is current while all of that is unchanged; otherwise it says what
# changed, so only that has to be checked again.

SEVERITIES = {"minor", "moderate", "major"}


def audit_file(ledger: Ledger, cid: str) -> Path:
    return ledger.root / "audits" / f"{cid}.json"


def load_audits(ledger: Ledger, cid: str) -> list[dict[str, Any]]:
    file = audit_file(ledger, cid)
    if not file.is_file():
        return []
    try:
        return json.loads(file.read_text(encoding="utf-8")).get("audits") or []
    except json.JSONDecodeError:
        raise LedgerError(f"audits/{cid}.json is not valid JSON")


def chain_below(claims: dict[str, dict[str, Any]], cid: str) -> list[str]:
    """Every ledger claim `cid` rests on, directly or not."""
    seen: list[str] = []

    def walk(x: str) -> None:
        for c in claims.get(x, {}).get("citations") or []:
            other = c.get("local")
            if other in claims and other not in seen and other != cid:
                seen.append(other)
                walk(other)

    walk(cid)
    return sorted(seen)


def chain_snapshot(
    ledger: Ledger, claims: dict[str, dict[str, Any]], cid: str
) -> dict[str, Any]:
    below = chain_below(claims, cid)
    chain = [cid, *below]
    reviews = sorted(
        {c["review"] for x in chain for c in claims[x].get("citations") or [] if c.get("review")}
    )
    papers = {
        source_key(c["external"])[0]
        for x in chain
        for c in claims[x].get("citations") or []
        if c.get("external") and PAPER_FORM.match(c["external"])
    }
    refuters = sorted(
        x
        for x, other in claims.items()
        for c in other.get("citations") or []
        if c.get("relation") == "refutes" and c.get("local") in chain
    )
    return {
        "seal": (claims[cid].get("seal") or {}).get("sha256"),
        "below": {x: (claims[x].get("seal") or {}).get("sha256") for x in below},
        "reviews": {rel: review_digest(ledger, rel) for rel in reviews},
        "refuted_by": refuters,
        "known_reviews": sorted(
            rel
            for rel, r in ledger.source_reviews().items()
            if r.get("source") in papers
        ),
    }


def audit_state(
    ledger: Ledger, claims: dict[str, dict[str, Any]], cid: str
) -> tuple[str, list[str]]:
    """('current' | 'stale' | 'never' | 'draft', what changed)."""
    claim = claims[cid]
    if claim.get("status") != "sealed":
        return "draft", []
    audits = load_audits(ledger, cid)
    if not audits:
        return "never", []
    last, now = audits[-1], chain_snapshot(ledger, claims, cid)
    why: list[str] = []
    if last.get("seal") != now["seal"]:
        why.append("the claim itself changed (its seal differs)")
    for x, seal in now["below"].items():
        if x not in last.get("below", {}):
            why.append(f"{x} is new below it")
        elif last["below"][x] != seal:
            why.append(f"{x}, which it rests on, changed")
    for rel, digest in now["reviews"].items():
        if last.get("reviews", {}).get(rel) != digest:
            why.append(f"the review {rel} changed")
    for x in now["refuted_by"]:
        if x not in last.get("refuted_by", []):
            why.append(f"{x} refutes it or something it rests on")
    reviews = ledger.source_reviews()
    for rel in now["known_reviews"]:
        verdict = reviews.get(rel, {}).get("verdict")
        if rel not in last.get("known_reviews", []) and verdict in ("fails", "holds_with_correction"):
            why.append(f"a new review of a paper it uses found a passage wrong: {rel}")
    return ("stale" if why else "current"), why


def check_findings(findings: Any) -> list[dict[str, Any]]:
    if not isinstance(findings, list):
        raise LedgerError("findings are a JSON list (empty when the claim holds up)")
    for n, f in enumerate(findings, start=1):
        if not isinstance(f, dict) or not (f.get("text") or "").strip():
            raise LedgerError(f"finding {n}: needs 'text' — what is wrong and why")
        if f.get("severity") not in SEVERITIES:
            raise LedgerError(f"finding {n}: severity is one of {sorted(SEVERITIES)}")
    return findings


def cmd_audit(ledger: Ledger, a: argparse.Namespace) -> int:
    claims = ledger.all()
    if a.id not in claims:
        raise LedgerError(f"no claim {a.id!r} in {ledger.root}")
    if claims[a.id].get("status") != "sealed":
        raise LedgerError(f"{a.id} is a draft: a draft changes, so an audit of it would not last")
    r = check(ledger, [a.id])
    if r.errors:
        print_report(r)
        raise LedgerError(f"{a.id} does not pass check; fix the record before auditing it")
    if a.clean:
        findings: list[dict[str, Any]] = []
    else:
        try:
            findings = check_findings(json.loads(Path(a.findings).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"cannot read the findings from {a.findings}: {exc}")
    entry = {
        "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "auditor": {"agent": a.agent, "human": a.human},
        "scope": a.scope,
        "findings": findings,
        **chain_snapshot(ledger, claims, a.id),
    }
    file = audit_file(ledger, a.id)
    file.parent.mkdir(parents=True, exist_ok=True)
    audits = load_audits(ledger, a.id) + [entry]
    file.write_text(
        json.dumps({"claim": a.id, "audits": audits}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    worst = max((f["severity"] for f in findings), key=["minor", "moderate", "major"].index,
                default=None)
    print(f"{file.relative_to(ledger.root)}: {len(findings)} finding(s)"
          + (f", worst {worst}" if worst else ""))
    return 0


def cmd_audit_status(ledger: Ledger, a: argparse.Namespace) -> int:
    """Which sealed claims need checking, and why — everything else was
    audited and nothing it rests on has changed since."""
    claims = {k: v for k, v in ledger.all().items() if not v.get("_unreadable")}
    ids = a.ids or sorted(claims)
    counts = {"current": 0, "stale": 0, "never": 0, "draft": 0}
    for cid in ids:
        if cid not in claims:
            raise LedgerError(f"no claim {cid!r} in {ledger.root}")
        state, why = audit_state(ledger, claims, cid)
        counts[state] += 1
        if state == "current" and not a.all:
            continue
        if state == "draft" and not a.all:
            continue
        line = {"current": "current", "stale": "STALE  ", "never": "never  ", "draft": "draft  "}[state]
        print(f"{line} {cid}")
        for reason in why:
            print(f"          {reason}")
    print(
        f"{counts['never']} never audited, {counts['stale']} stale, "
        f"{counts['current']} current, {counts['draft']} draft(s)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="claims.py", description="Record, check and publish findings as claims."
    )
    p.add_argument("--root", help="the ledger folder (default: claims/ at the git root)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("new", help="start a draft claim; prints its id and folder")
    s.add_argument("title")
    s.add_argument("--type", choices=sorted(CLAIM_TYPES))
    s.add_argument("--slug", help="a few words for the id (default: from the title)")
    s.add_argument(
        "--date",
        help="when the finding was made, YYYY-MM-DD, if not today: the date of "
        "the run, for a finding recorded after the fact",
    )
    s.set_defaults(run=cmd_new)

    s = sub.add_parser("check", help="check claims (all, or the ids given)")
    s.add_argument("ids", nargs="*")
    s.set_defaults(run=cmd_check)

    s = sub.add_parser("seal", help="freeze a draft: no change after this")
    s.add_argument("id")
    s.set_defaults(run=cmd_seal)

    s = sub.add_parser("trace", help="everything a claim rests on, as a tree")
    s.add_argument("id")
    s.set_defaults(run=cmd_trace)

    s = sub.add_parser("index", help="write claims/README.md: the list and the graph")
    s.set_defaults(run=cmd_index)

    s = sub.add_parser("order", help="what to publish first, for this claim")
    s.add_argument("id")
    s.set_defaults(run=cmd_order)

    s = sub.add_parser("payload", help="the publish_claim arguments for a sealed claim")
    s.add_argument("id")
    group = s.add_mutually_exclusive_group()
    group.add_argument("--space-id", help="publish into this team space")
    group.add_argument("--public", action="store_true", help="publish publicly")
    s.set_defaults(run=cmd_payload)

    s = sub.add_parser("published", help="record the Library id a claim was given")
    s.add_argument("id")
    s.add_argument("library_id")
    s.add_argument("--visibility", default="private", choices=["private", "public"])
    s.set_defaults(run=cmd_published)

    s = sub.add_parser("pending", help="draft claims not yet sealed, with their check")
    s.set_defaults(run=cmd_pending)

    s = sub.add_parser("recall", help="what the ledger already says about something")
    s.add_argument("query", nargs="*", help="words, a number, a parameter name")
    s.add_argument("--exact", action="store_true",
                   help="every claim containing the query as written, unranked")
    s.add_argument("--titles", action="store_true",
                   help="every claim's title, newest first: the overview")
    s.add_argument("--limit", type=int, default=10, help="claims shown (default 10)")
    s.add_argument("--lines", type=int, default=3, help="matching lines per claim")
    s.set_defaults(run=cmd_recall)

    s = sub.add_parser("audit", help="record what check-claims found for a sealed claim")
    s.add_argument("id")
    group = s.add_mutually_exclusive_group(required=True)
    group.add_argument("--findings", help="a JSON list of {severity, text, quote, file}")
    group.add_argument("--clean", action="store_true", help="no findings: it holds up")
    s.add_argument("--agent", required=True, help="who audited it: the agent and its model id")
    s.add_argument("--human", help="a person who checked the audit, if any")
    s.add_argument("--scope", default="full", choices=["full", "chain"],
                   help="'chain': only re-checked what changed below it")
    s.set_defaults(run=cmd_audit)

    s = sub.add_parser("audit-status", help="which sealed claims need checking, and why")
    s.add_argument("ids", nargs="*")
    s.add_argument("--all", action="store_true", help="also list current audits and drafts")
    s.set_defaults(run=cmd_audit_status)

    conv = sub.add_parser("conv", help="the project's conventions (conventions.json)")
    csub = conv.add_subparsers(dest="conv_command", required=True)
    s = csub.add_parser("list", help="the newest version of each convention")
    s.set_defaults(run=cmd_conv_list)
    s = csub.add_parser("add", help="define a new convention, as version 1")
    s.add_argument("key")
    s.add_argument("statement")
    s.add_argument("--category", help="units, fourier, normalisation, sign, notation, …")
    s.set_defaults(run=cmd_conv_add)
    s = csub.add_parser("revise", help="a changed convention: its next version")
    s.add_argument("key")
    s.add_argument("statement")
    s.add_argument("--why", required=True, help="why it changed")
    s.set_defaults(run=cmd_conv_revise)
    s = csub.add_parser("show", help="every version of one, and the claims using each")
    s.add_argument("key")
    s.set_defaults(run=cmd_conv_show)

    src = sub.add_parser("source", help="reviews of papers the claims rest on")
    ssub = src.add_subparsers(dest="source_command", required=True)
    s = ssub.add_parser("new", help="start a review of a passage; prints its path")
    s.add_argument("source", help="arxiv:…, doi:10.… or an arxiv.org / doi.org link")
    s.add_argument("--locator", help="the passage: 'Eq. (12)', 'Table II'")
    s.add_argument("--slug", help="a few words for the file name")
    s.add_argument("--date", help="when the review was done, YYYY-MM-DD, if not today")
    s.set_defaults(run=cmd_source_new)
    s = ssub.add_parser("list", help="the source reviews (of one paper, if given)")
    s.add_argument("source", nargs="?")
    s.set_defaults(run=cmd_source_list)
    s = ssub.add_parser("payload", help="the review_source arguments for a review")
    s.add_argument("path", help="sources/<paper>/<review>.json")
    group = s.add_mutually_exclusive_group()
    group.add_argument("--space-id", help="publish into this team space")
    group.add_argument("--public", action="store_true", help="publish publicly")
    s.set_defaults(run=cmd_source_payload)
    s = ssub.add_parser("published", help="record the Library id a review was given")
    s.add_argument("path")
    s.add_argument("library_id")
    s.add_argument("--visibility", default="private", choices=["private", "public"])
    s.set_defaults(run=cmd_source_published)

    a = p.parse_args(argv)
    ledger = Ledger(ledger_root(a.root))
    try:
        return a.run(ledger, a)
    except LedgerError as exc:
        print(f"claims.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
