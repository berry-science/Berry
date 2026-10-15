"""The labbook generator: claims as data in, LaTeX out.

Shared by two callers, so a labbook looks the same wherever it is built:

- `labbook.py` in this skill, which reads a claim ledger (claims/) and
  writes `claims.gen.tex` beside the researcher's own `labbook.tex`;
- the Berry Science Library, which reads claims from its database, writes
  the whole document — the steps an agent added one at a time, in the
  researcher's voice — and compiles it on its render service.

Nothing here reads or writes a file, or knows where the data came from.
Every value is plain data (dicts, lists, strings), and every piece of it
that came from a person or an agent is escaped before it reaches LaTeX:
`tex()` for plain text, `markdown()` for step prose, which allows a small
Markdown subset and inline mathematics from an allow-list of commands, and
nothing else. The Library compiles what agents write; LaTeX that reads
files or runs commands must not get through.

Standard library only; Python 3.9+. The Library builds its labbooks with
an exact copy of this file — change it here, never there. CORE_VERSION
goes up with every change that alters the output.
"""

from __future__ import annotations

import json
import re
from typing import Any

CORE_VERSION = "3"

# --- figures -------------------------------------------------------------------------

# The width a figure is drawn at, in Vega-Lite pixels (= PDF points); the
# document scales it to 0.92 \linewidth, so text in it comes out near its
# set size. The sans of the labels and the Library's four categorical
# figure colors (the Berry Science design tokens --figure-1 … --figure-4).
FIGURE_WIDTH = 400
FIGURE_HEIGHT = 240
FIGURE_FONT = "IBM Plex Sans"
FIGURE_COLOURS = ["#1666AA", "#BB731B", "#7B489E", "#548436"]
PAPER = "#FBFAF6"


def print_theme(spec: dict[str, Any]) -> dict[str, Any]:
    """A web Vega-Lite spec, set for paper: the document's sans, the
    paper tone, the figure colors, a fixed size where the web spec fills
    its container. The data is never touched."""
    spec = json.loads(json.dumps(spec))
    config = spec.setdefault("config", {})
    config.setdefault("font", FIGURE_FONT)
    config.setdefault("background", PAPER)
    config.setdefault("range", {}).setdefault("category", FIGURE_COLOURS)
    config.setdefault("view", {}).setdefault("stroke", None)
    composite = any(k in spec for k in ("facet", "repeat", "concat", "hconcat", "vconcat"))
    if not composite:
        if spec.get("width") in (None, "container"):
            spec["width"] = FIGURE_WIDTH
        if spec.get("height") in (None, "container"):
            spec["height"] = FIGURE_HEIGHT
    spec.pop("autosize", None)
    return spec


def figure_name(claim_id: str, n: int) -> str:
    return f"figures/{claim_id}-{n:02d}.pdf"


# --- plain text --------------------------------------------------------------------------

_TEX = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex(text: str | None, *, strip: bool = True) -> str:
    """Plain text as LaTeX: every special character escaped, a blank line a
    paragraph. LuaLaTeX takes the Unicode (µ, ², ∫) as it is. `strip=False`
    for a piece of a line, whose spaces separate it from its neighbors."""
    if not text:
        return ""
    out = "".join(_TEX.get(ch, ch) for ch in (text.strip() if strip else text))
    out = re.sub(r"\n\s*\n", r"\\par ", out)
    return out.replace("\n", " ")


def tex_url(url: str) -> str:
    """A URL inside \\href: only characters that cannot break out of it."""
    url = re.sub(r"[^A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]", "", url)
    return url.replace("\\", "").replace("%", r"\%").replace("#", r"\#").replace("{", "").replace("}", "")


def macro_id(value: str) -> str:
    """An id as it may appear inside \\csname … and \\label: letters, digits,
    '-', '.', '/'. Ledger ids, Library uuids and source paths all are."""
    if not re.fullmatch(r"[A-Za-z0-9./-]+", value or ""):
        raise ValueError(f"not usable as an id in LaTeX: {value!r}")
    return value


# --- step prose: a small, safe Markdown ---------------------------------------------------

# Inside $…$ only these commands, and no braces games: enough for the
# mathematics a step's prose needs (ω = 2π f, \sqrt{k/m}, x_1^2).
MATH_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi",
    "rho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi",
    "Omega", "hbar", "ell", "partial", "nabla", "infty", "cdot", "times",
    "pm", "mp", "leq", "geq", "neq", "approx", "sim", "propto", "equiv",
    "ll", "gg", "to", "rightarrow", "leftarrow", "Rightarrow", "langle",
    "rangle", "sum", "prod", "int", "oint", "sqrt", "frac", "mathrm",
    "mathbf", "mathit", "mathcal", "text", "left", "right", "quad", "qquad",
    "log", "ln", "exp", "sin", "cos", "tan", "max", "min", "lim", "dot",
    "ddot", "hat", "bar", "vec", "tilde", "prime", "circ", "degree",
}
_MATH = re.compile(r"(?<!\\)\$([^$\n]{1,400})\$")
_MATH_CMD = re.compile(r"\\([A-Za-z]+)")


def _math(body: str) -> str | None:
    """$…$ content if every command in it is allowed, else None (the whole
    span is then printed as text)."""
    if "\\\\" in body or re.search(r"[#%&~]", body):
        return None
    for name in _MATH_CMD.findall(body):
        if name not in MATH_COMMANDS:
            return None
    if body.count("{") != body.count("}"):
        return None
    return f"${body}$"


def _inline(text: str) -> str:
    """One line of Markdown: math, `code`, **bold**, *italic*, [[claim:id]]
    references; everything else escaped."""
    out: list[str] = []
    pos = 0
    pattern = re.compile(
        r"(?P<math>(?<!\\)\$[^$\n]{1,400}\$)|(?P<code>`[^`\n]{1,200}`)"
        r"|(?P<bold>\*\*[^*\n]{1,400}\*\*)|(?P<ital>\*[^*\n]{1,400}\*)"
        r"|(?P<ref>\[\[claim:[A-Za-z0-9-]{1,64}\]\])"
    )
    for m in pattern.finditer(text):
        out.append(tex(text[pos : m.start()], strip=False) if m.start() > pos else "")
        token = m.group(0)
        if m.group("math"):
            out.append(_math(token[1:-1]) or tex(token))
        elif m.group("code"):
            out.append(r"\texttt{" + tex(token[1:-1]) + "}")
        elif m.group("bold"):
            out.append(r"\textbf{" + tex(token[2:-2]) + "}")
        elif m.group("ital"):
            out.append(r"\emph{" + tex(token[1:-1]) + "}")
        else:
            out.append(r"\claimref{" + macro_id(token[len("[[claim:") : -2]) + "}")
        pos = m.end()
    out.append(tex(text[pos:], strip=False))
    return "".join(out)


def markdown(text: str | None) -> str:
    """Step prose as LaTeX. Paragraphs, bullet lists ('- '), numbered lists
    ('1. '), **bold**, *italic*, `code`, $math$ from MATH_COMMANDS, and
    [[claim:<id>]] references. Nothing else reaches LaTeX unescaped."""
    if not text:
        return ""
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if all(re.match(r"^\s*[-*] ", ln) for ln in lines):
            items = "".join(r"\item " + _inline(re.sub(r"^\s*[-*] ", "", ln)) + "\n" for ln in lines)
            blocks.append("\\begin{itemize}\n" + items + "\\end{itemize}")
        elif all(re.match(r"^\s*\d+[.)] ", ln) for ln in lines):
            items = "".join(r"\item " + _inline(re.sub(r"^\s*\d+[.)] ", "", ln)) + "\n" for ln in lines)
            blocks.append("\\begin{enumerate}\n" + items + "\\end{enumerate}")
        else:
            blocks.append(" ".join(_inline(ln.strip()) for ln in lines))
    return "\n\n".join(blocks)


# --- what the ledger or the Library says, as LaTeX definitions ----------------------------
#
# A claim, as both callers hand it over:
#
#   {"id", "title", "statement", "holds_when", "claim_type",
#    "status": "sealed" | "draft",  "seal": "first 8 of the hash" | None,
#    "links": [{"text", "url"}],          # ledger file, Library page
#    "conventions": ["key@version", …],
#    "citations": [{"relation", "local": id | None, "external": str | None,
#                   "url": str | None, "locator", "verdict"}],
#    "figures": [{"n", "file": "figures/….pdf" | "", "caption"}]}
#
# A review of a paper: {"id", "source", "source_version", "locator",
# "verdict", "summary", "url"}. A convention version: {"key", "version",
# "statement", "since", "why"}.

VERDICT = {
    "holds": ("\\berryVerdictholds", "berryink"),
    "holds_with_correction": ("\\berryVerdictholdswithcorrection", "berrycorrected"),
    "fails": ("\\berryVerdictfails", "berrywithdrawn"),
    "could_not_check": ("\\berryVerdictcouldnotcheck", "berrymuted"),
}


def claim_order(claims: list[dict[str, Any]]) -> list[str]:
    """Each claim after what it rests on; otherwise in the order given."""
    by_id = {c["id"]: c for c in claims}
    order: list[str] = []

    def visit(cid: str, seen: set[str]) -> None:
        if cid in order or cid in seen:
            return
        seen.add(cid)
        for c in by_id[cid].get("citations") or []:
            if c.get("local") in by_id:
                visit(c["local"], seen)
        order.append(cid)

    for c in claims:
        visit(c["id"], set())
    return order


def _claim_type(claim: dict[str, Any]) -> str:
    kind = (claim.get("claim_type") or "").replace("_", "")
    return f"\\berryType{kind}{{}}" if kind.isalpha() else "\\berryClaim"


def _rests_on(claim: dict[str, Any], known: set[str]) -> str:
    parts = []
    for c in claim.get("citations") or []:
        relation = c.get("relation", "cites")
        rel = f"\\berryRel{relation}{{}}" if relation.isalpha() else tex(relation)
        if c.get("local") and c["local"] in known:
            parts.append(f"{rel} \\claimref{{{macro_id(c['local'])}}}")
            continue
        target = c.get("external") or c.get("local") or ""
        url = c.get("url") or (target if target.startswith("http") else None)
        if url and "/commit/" in url:
            short = url.rstrip("/").rsplit("/", 1)[-1][:7]
            text = f"\\href{{{tex_url(url)}}}{{code \\texttt{{{tex(short)}}}}}"
        elif url:
            label = target if not target.startswith("http") else url
            text = f"\\href{{{tex_url(url)}}}{{{tex(label)}}}"
        else:
            text = tex(target)
        if c.get("locator"):
            text += f", {tex(c['locator'])}"
        if c.get("verdict"):
            word, color = VERDICT.get(c["verdict"], ("?", "berrymuted"))
            text += f" (\\textcolor{{{color}}}{{{word}}})"
        parts.append(f"{rel} {text}")
    return "; ".join(parts)


def _table(name: str, widths: tuple[float, ...], rows: list[str]) -> list[str]:
    if not rows:
        return [f"\\newcommand{{\\{name}}}{{}}"]
    cols = "".join(f"p{{{w}\\linewidth}}" for w in widths)
    return [
        f"\\newcommand{{\\{name}}}{{%",
        f"\\begin{{small}}\\begin{{longtable}}{{@{{}}{cols}@{{}}}}",
        "\\toprule",
        *rows,
        "\\bottomrule",
        "\\end{longtable}\\end{small}}",
    ]


def definitions(
    claims: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    conventions: list[dict[str, Any]],
    *,
    source: str = "claims/",
) -> str:
    """claims.gen.tex: one \\berrydefclaim per claim, its figures, the
    papers checked, the overview and the conventions table."""
    order = claim_order(claims)
    by_id = {c["id"]: c for c in claims}
    known = set(by_id)
    lines = [
        f"% Generated from {source} by labbook_core {CORE_VERSION} — do not edit by hand.",
        "",
    ]
    for cid in order:
        c = by_id[cid]
        macro_id(cid)
        status = (
            f"\\berrySealed\\ \\texttt{{{tex(c.get('seal') or '')}}}"
            if c.get("status") == "sealed" and c.get("seal")
            else "\\berrySealed"
            if c.get("status") == "sealed"
            else "\\textit{\\berryDraft}"
        )
        links = "\\ ·\\ ".join(
            f"\\href{{{tex_url(link['url'])}}}{{{link['text']}}}" for link in c.get("links") or []
        )
        conv = ", ".join(f"\\texttt{{{tex(ref)}}}" for ref in c.get("conventions") or [])
        # How \claimref prints it: the ledger id (a date and words), or a
        # short form of a Library uuid.
        lines.append(f"\\berrydeflabel{{{cid}}}{{{tex(c.get('label') or cid)}}}")
        lines.append(
            f"\\berrydefclaim{{{cid}}}{{{tex(c.get('title'))}}}"
            f"{{{tex(c.get('statement'))}}}{{{tex(c.get('holds_when'))}}}"
            f"{{{_claim_type(c)}}}{{{status}}}{{{links}}}"
            f"{{{conv}}}{{{_rests_on(c, known)}}}"
        )
        figs = []
        for fig in c.get("figures") or []:
            n = int(fig["n"])
            file_ref = fig.get("file") or ""
            if file_ref and not re.fullmatch(r"figures/[A-Za-z0-9._-]+\.pdf", file_ref):
                raise ValueError(f"not a figure path: {file_ref!r}")
            lines.append(
                f"\\berrydeffigure{{{cid}}}{{{n}}}{{{file_ref}}}{{{tex(fig.get('caption'))}}}"
            )
            figs.append(f"\\claimfigure{{{cid}}}{{{n}}}")
        lines.append(f"\\expandafter\\def\\csname berry@figs@{cid}\\endcsname{{{''.join(figs)}}}")

    for r in reviews:
        word, color = VERDICT.get(r.get("verdict") or "", ("?", "berrymuted"))
        link = f"\\href{{{tex_url(r['url'])}}}{{\\berryInLibrary}}" if r.get("url") else ""
        lines.append(
            f"\\berrydefsource{{{macro_id(r['id'])}}}{{{tex(r.get('source'))}"
            f"{tex(r.get('source_version') or '')}}}"
            f"{{{tex(r.get('locator') or '—')}}}{{{word}}}{{{color}}}"
            f"{{{tex(r.get('summary'))}}}{{{link}}}"
        )

    rows = []
    for cid in order:
        c = by_id[cid]
        state = "\\berrySealed" if c.get("status") == "sealed" else "\\berryDraft"
        rows.append(
            f"{tex(c.get('date') or cid[:10])} & \\hyperref[claim:{cid}]{{{tex(c.get('title'))}}} & {state}\\\\"
        )
    lines += ["", *_table("berryoverview", (0.13, 0.62, 0.2), rows)]

    conv_rows = []
    for v in conventions:
        why = (
            f" \\newline\\textcolor{{berrymuted}}{{\\footnotesize {tex(v['why'])}}}"
            if v.get("why")
            else ""
        )
        conv_rows.append(
            f"\\texttt{{{tex(v.get('key'))}@{v.get('version')}}} & {tex(v.get('statement'))}{why}"
            f" & {tex(v.get('since') or '')}\\\\"
        )
    lines += ["", *_table("berryconventions", (0.25, 0.57, 0.13), conv_rows)]
    return "\n".join(lines) + "\n"


# --- a whole document, from steps (the Library) ------------------------------------------------

LABELS = {
    "en": {},
    "de": {
        "berryHoldsWhen": "Gilt, wenn",
        "berryConventions": "Konventionen",
        "berryRestsOn": "Beruht auf",
        "berryDraft": "Entwurf — noch nicht abgestimmt",
        "berrySealed": "versiegelt",
        "berryInLibrary": "in der Library",
        "berryFigureMissing": "Abbildung nicht erzeugt",
        "berryMissingClaim": "Kein Claim mit dieser Id",
        "berryPaperReview": "Paper geprüft",
        "berryVerdictholds": "stimmt",
        "berryVerdictholdswithcorrection": "stimmt mit Korrektur",
        "berryVerdictfails": "falsch — nicht verwendet",
        "berryVerdictcouldnotcheck": "nicht prüfbar",
        "berryEvidence": "Evidenz",
        "berryRelcites": "zitiert",
        "berryReluses": "verwendet",
        "berryRelextends": "erweitert",
        "berryRelreplicates": "repliziert",
        "berryRelrefutes": "widerlegt",
        "berryTyperesult": "Ergebnis",
        "berryTypemethod": "Methode",
        "berryTypenegativeresult": "negatives Ergebnis",
        "berryTypecalibration": "Kalibrierung",
    },
}
HEADINGS = {
    "en": {"stand": "Where things stand", "open": "Open points and follow-up questions",
           "notes": "Notes", "conventions": "Conventions", "babel": "english"},
    "de": {"stand": "Stand", "open": "Offene Punkte und Folgefragen",
           "notes": "Notizen", "conventions": "Konventionen", "babel": "ngerman"},
}


def document(labbook: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """labbook.tex for a labbook kept in the Library.

    `labbook`: {"title", "author", "language": "en" | "de",
    "where_things_stand", "open_points", "notes"} — the last three
    Markdown. Notes are what the researcher asked to have written down
    beyond the claims; they come last, after the open points, and only
    when there are any.
    `steps`, in order: {"heading", "why", "what", "means" (Markdown),
    "claim_id" | None, "sources": [review ids the claim cites]}.
    """
    lang = str(labbook.get("language") or "en")
    if lang not in HEADINGS:
        lang = "en"
    h = HEADINGS[lang]
    out = [
        "% Generated by the Berry Science Library (labbook_core "
        f"{CORE_VERSION}). The steps were written one claim at a time.",
        "\\documentclass[11pt,a4paper]{article}",
        f"\\usepackage[{h['babel']}]{{babel}}",
        "\\usepackage{berry-labbook}",
    ]
    out += [f"\\renewcommand{{\\{k}}}{{{v}}}" for k, v in LABELS[lang].items()]
    out += [
        "\\input{claims.gen.tex}",
        f"\\title{{{tex(labbook.get('title'))}}}",
        f"\\author{{{tex(labbook.get('author') or '')}}}",
        "\\date{\\today}",
        "\\begin{document}",
        "\\maketitle",
        f"\\section*{{{h['stand']}}}",
        markdown(labbook.get("where_things_stand")),
        "",
        "\\berryoverview",
        "",
    ]
    for step in steps:
        out.append(f"\\section{{{tex(step.get('heading'))}}}")
        for part in ("why", "what"):
            if step.get(part):
                out += [markdown(step[part]), ""]
        for rid in step.get("sources") or []:
            out.append(f"\\sourcebox{{{macro_id(rid)}}}")
        if step.get("claim_id"):
            cid = macro_id(step["claim_id"])
            out += [f"\\claimbox{{{cid}}}", f"\\claimfigures{{{cid}}}", ""]
        if step.get("means"):
            out += [markdown(step["means"]), ""]
    out += [
        f"\\section*{{{h['open']}}}",
        markdown(labbook.get("open_points")),
        "",
    ]
    if labbook.get("notes"):
        out += [f"\\section*{{{h['notes']}}}", markdown(labbook["notes"]), ""]
    out += [
        "\\appendix",
        f"\\section{{{h['conventions']}}}",
        "\\berryconventions",
        "\\end{document}",
    ]
    return "\n".join(out) + "\n"
