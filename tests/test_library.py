"""Tests for skills/claims/scripts/library.py: login, where, publish.

No network: the Library and its authorization server are a fake, an
http.server in a thread on 127.0.0.1.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "claims" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import claims  # noqa: E402
import library  # noqa: E402

PERSONAL = "aaaaaaaa-0000-0000-0000-000000000001"
TEAM = "bbbbbbbb-0000-0000-0000-000000000002"
TEAM_BOOK = "cccccccc-0000-0000-0000-000000000003"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeLibrary:
    """The API (claims, spaces, labbooks) and the authorization server."""

    def __init__(self) -> None:
        self.claims: dict[str, dict] = {}
        self.keys: dict[str, tuple[str, str]] = {}  # client_key -> (content, id)
        self.posts: list[dict] = []
        self.accepted = {"good"}
        self.refreshes = 0
        self.drop_posts = 0
        self.tamper = None
        self.challenges: dict[str, str] = {}  # code -> PKCE challenge
        self.registered: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def reply(self, status: int, body) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def authorized(self) -> bool:
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                if token in fake.accepted:
                    return True
                self.reply(401, {"detail": "invalid token"})
                return False

            def body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_GET(self) -> None:  # noqa: N802
                base = f"http://127.0.0.1:{fake.port}"
                path = urllib.parse.urlsplit(self.path).path
                if path == "/.well-known/oauth-protected-resource/mcp":
                    return self.reply(200, {"resource": base + "/mcp",
                                            "authorization_servers": [base + "/auth/v1"]})
                if path == "/auth/v1/.well-known/oauth-authorization-server":
                    return self.reply(200, {
                        "issuer": base + "/auth/v1",
                        "authorization_endpoint": base + "/auth/v1/oauth/authorize",
                        "token_endpoint": base + "/auth/v1/oauth/token",
                        "registration_endpoint": base + "/auth/v1/oauth/clients/register",
                    })
                if not self.authorized():
                    return
                if path == "/spaces":
                    return self.reply(200, [
                        {"id": PERSONAL, "name": "Library", "personal": True, "role": "owner"},
                        {"id": TEAM, "name": "Atoms", "personal": False, "role": "member"},
                    ])
                if path == "/labbooks":
                    return self.reply(200, [{"id": TEAM_BOOK, "title": "Transport", "space_id": TEAM,
                                             "space_name": "Atoms", "claims": 2}])
                if path == "/authors/me":
                    return self.reply(200, {"display_name": "A. Author"})
                if path.startswith("/claims/"):
                    detail = json.loads(json.dumps(fake.claims[path.split("/")[2]]))
                    if fake.tamper:
                        fake.tamper(detail)
                    return self.reply(200, detail)
                self.reply(404, {"detail": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urllib.parse.urlsplit(self.path).path
                raw = self.body()
                if path == "/auth/v1/oauth/clients/register":
                    req = json.loads(raw)
                    fake.registered.append(req)
                    return self.reply(201, {"client_id": "client-1", **req})
                if path == "/auth/v1/oauth/token":
                    form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                    if form["grant_type"] == "refresh_token" and form["refresh_token"] == "r1":
                        fake.refreshes += 1
                        fake.accepted.add("fresh")
                        return self.reply(200, {"access_token": "fresh", "refresh_token": "r2",
                                                "expires_in": 3600})
                    if form["grant_type"] == "authorization_code":
                        challenge = fake.challenges.get(form["code"])
                        if challenge and library.code_challenge(form["code_verifier"]) == challenge:
                            return self.reply(200, {"access_token": "good", "refresh_token": "r1",
                                                    "expires_in": 3600})
                    return self.reply(400, {"error": "invalid_grant"})
                if not self.authorized():
                    return
                if path == "/claims":
                    if fake.drop_posts:
                        fake.drop_posts -= 1
                        self.close_connection = True
                        return  # no answer at all: the client sees the connection drop
                    payload = json.loads(raw)
                    fake.posts.append(payload)
                    content = json.dumps({k: v for k, v in payload.items() if k != "client_key"},
                                         sort_keys=True)
                    key = payload.get("client_key")
                    if key in fake.keys:
                        seen, cid = fake.keys[key]
                        if seen == content:
                            return self.reply(200, fake.claims[cid])
                        return self.reply(409, {"detail": "client_key names another claim"})
                    cid = str(uuid.uuid4())
                    fake.claims[cid] = fake.detail(cid, payload)
                    if key:
                        fake.keys[key] = (content, cid)
                    return self.reply(201, fake.claims[cid])
                self.reply(404, {"detail": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    @staticmethod
    def detail(cid: str, p: dict) -> dict:
        return {
            "id": cid,
            "title": p["title"],
            "statement": p["statement"],
            "claim_type": p.get("claim_type"),
            "holds_when": p.get("holds_when"),
            "visibility": "private" if p.get("private") or p.get("space_id") else "public",
            "space_id": p.get("space_id"),
            "labbook_id": p.get("labbook_id"),
            "evidence": [
                {"id": str(uuid.uuid4()), "ordinal": i, "kind": e["kind"], "content": e.get("content"),
                 "format": e.get("format", "plain"), "language": e.get("language"),
                 "caption": e.get("caption"), "deleted_at": None}
                for i, e in enumerate(p.get("evidence") or [])
            ],
            "citations": [
                {"ordinal": i + 1, "cited_claim_id": c.get("claim_id"), "external": c.get("external"),
                 "label": c.get("label"), "relation": c.get("relation", "cites"),
                 "reason": c.get("reason"), "locator": c.get("locator"),
                 "source_review_id": c.get("source_review_id")}
                for i, c in enumerate(p.get("citations") or [])
            ],
            "conventions": [dict(c, category=c.get("category")) for c in p.get("conventions") or []],
        }


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.repo = tmp / "proj"
        self.repo.mkdir()
        self.root = self.repo / "claims"
        self.fake = FakeLibrary()
        env = mock.patch.dict(os.environ, {
            "BERRY_API_URL": self.fake.url,
            "BERRY_WEB_URL": "https://berry.test",
            "XDG_CONFIG_HOME": str(tmp / "config"),
        })
        env.start()
        self.addCleanup(env.stop)
        delays = mock.patch.object(library, "RETRY_DELAYS", (0, 0, 0))
        delays.start()
        self.addCleanup(delays.stop)

    def tearDown(self) -> None:
        self.fake.close()
        self.tmp.cleanup()

    def run_cli(self, *args: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = claims.main(["--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def sign_in(self, access: str = "good", expires_at: int | None = None) -> None:
        library.update_credentials(
            self.fake.url,
            client={"client_id": "client-1",
                    "token_endpoint": self.fake.url + "/auth/v1/oauth/token"},
            tokens={"access_token": access, "refresh_token": "r1",
                    "expires_at": expires_at or 4_000_000_000},
        )


class LedgerBase(Base):
    def setUp(self) -> None:
        super().setUp()
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "config", "user.email", "t@example.org"], check=True)
        subprocess.run([*git, "config", "user.name", "t"], check=True)
        subprocess.run([*git, "remote", "add", "origin", "git@github.com:Lab/Proj.git"], check=True)
        (self.repo / "sim.py").write_text("print(31.1)\n")
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "sim"], check=True)

    def sealed(self, title: str, **fields) -> str:
        # The JSON draft: this helper edits claim.json directly, which a
        # claim.md draft would compile over.
        code, out, _ = self.run_cli("new", title, "--type", "result", "--json")
        self.assertEqual(code, 0)
        cid = out.splitlines()[0]
        folder = self.root / cid
        (folder / "evidence" / "01-reasoning.md").write_text("The residual is 31.1 um.")
        (folder / "evidence" / "02-output.txt").write_text("residual 31.1 um\n")
        claim = json.loads((folder / "claim.json").read_text())
        claim.update(statement="The residual is 31.1 um.", holds_when="Simulation, linear ramp.")
        claim["evidence"].append({"kind": "output", "file": "evidence/02-output.txt", "caption": "Run log"})
        claim.update(fields)
        (folder / "claim.json").write_text(json.dumps(claim, indent=2))
        code, out, err = self.run_cli("seal", cid, "--without-check")
        self.assertEqual(code, 0, out + err)
        return cid

    def load(self, cid: str) -> dict:
        return json.loads((self.root / cid / "claim.json").read_text())

    def consent(self) -> None:
        code, out, err = self.run_cli("where", "--consent", "yes")
        self.assertEqual(code, 0, out + err)


# --- the pieces ---------------------------------------------------------------


class PkceTest(unittest.TestCase):
    def test_the_rfc_7636_example(self) -> None:
        self.assertEqual(
            library.code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        )

    def test_a_pair_is_fresh_and_fits(self) -> None:
        v1, c1 = library.pkce_pair()
        v2, _ = library.pkce_pair()
        self.assertNotEqual(v1, v2)
        self.assertTrue(43 <= len(v1) <= 128)
        self.assertEqual(library.code_challenge(v1), c1)
        self.assertNotIn("=", c1)

    def test_the_redirect_must_carry_this_sign_ins_state(self) -> None:
        url = "http://127.0.0.1:53781/callback?code=abc&state=s1"
        self.assertEqual(library.code_from_redirect(url, "s1"), "abc")
        self.assertEqual(library.code_from_redirect("  code=abc&state=s1\n", "s1"), "abc")
        with self.assertRaisesRegex(library.LibraryError, "another sign-in"):
            library.code_from_redirect(url, "s2")
        with self.assertRaisesRegex(library.LibraryError, "refused: denied"):
            library.code_from_redirect("http://x/callback?error=access_denied&error_description=denied", "s1")


class RepoIdentityTest(unittest.TestCase):
    def test_every_form_of_the_same_remote_is_the_same_repository(self) -> None:
        for url in (
            "git@github.com:Lab/Proj.git",
            "https://github.com/Lab/Proj.git",
            "https://user:token@github.com/lab/proj/",
            "ssh://git@github.com/Lab/Proj.git",
            "github.com:Lab/Proj",
        ):
            self.assertEqual(library.normalise_remote(url), "github.com/lab/proj", url)
        self.assertEqual(library.normalise_remote("/srv/git/Proj.git"), "proj")
        self.assertEqual(library.normalise_remote("file:///srv/git/proj.git"), "proj")

    def test_a_key_stays_within_the_librarys_limit(self) -> None:
        self.assertEqual(library.client_key("github.com/a/b", "2026-10-10-x"), "ledger:github.com/a/b/2026-10-10-x")
        self.assertLessEqual(len(library.client_key("h/" + "x" * 300, "2026-10-10-x")), 200)

    def test_two_projects_in_one_repository_have_their_own_keys(self) -> None:
        """A repository holding several projects, each with its ledger in a
        subfolder: the same claim id in two of them must not share a key."""
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            git = ["git", "-C", str(top)]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run(
                [*git, "remote", "add", "origin", "git@github.com:Lab/Proj.git"], check=True
            )
            (top / "sbd").mkdir()
            here = library.repo_identity(top, claims.git)
            sub = library.repo_identity(top / "sbd", claims.git)
        self.assertEqual(here, "github.com/lab/proj")
        self.assertEqual(sub, "github.com/lab/proj/sbd")


class CredentialsTest(Base):
    def test_the_file_is_the_owners_alone_and_keyed_by_api(self) -> None:
        library.update_credentials("https://api.one", tokens={"access_token": "a"})
        library.update_credentials("https://api.two", tokens={"access_token": "b"})
        path = Path(self.tmp.name) / "config" / "berry" / "credentials.json"
        self.assertEqual(library.credentials_path(), path)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode) & 0o077, 0)
        data = json.loads(path.read_text())
        self.assertEqual(data["https://api.one"]["tokens"]["access_token"], "a")
        self.assertEqual(data["https://api.two"]["tokens"]["access_token"], "b")
        self.assertEqual(list(path.parent.iterdir()), [path])  # no temporary file left

    def test_logout_removes_the_tokens_and_keeps_the_client(self) -> None:
        self.sign_in()
        code, out, _ = self.run_cli("logout")
        self.assertEqual(code, 0)
        entry = library.credentials_for(self.fake.url)
        self.assertNotIn("tokens", entry)
        self.assertEqual(entry["client"]["client_id"], "client-1")


class LoginTest(Base):
    def setUp(self) -> None:
        super().setUp()
        port = free_port()
        ports = mock.patch.object(library, "LOOPBACK_PORTS", (port,))
        ports.start()
        self.addCleanup(ports.stop)

    def authorize(self, url: str) -> str:
        """What the authorization server does once the user approves: the
        address the browser is sent to."""
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertEqual(q["client_id"], "client-1")
        self.fake.challenges["code-1"] = q["code_challenge"]
        return f"{q['redirect_uri']}?code=code-1&state={q['state']}"

    def test_the_browser_lands_on_the_loopback(self) -> None:
        def browser(url: str) -> None:
            back = self.authorize(url)
            threading.Thread(target=lambda: urllib.request.urlopen(back).read(), daemon=True).start()

        r, w = os.pipe()
        with open(r) as stdin, open(w, "w"):
            tokens = library.login(self.fake.url, open_browser=browser, stdin=stdin, out=io.StringIO())
        self.assertEqual(tokens["access_token"], "good")
        entry = library.credentials_for(self.fake.url)
        self.assertEqual(entry["tokens"]["refresh_token"], "r1")
        self.assertEqual(entry["client"]["client_id"], "client-1")
        self.assertEqual(self.fake.registered[0]["token_endpoint_auth_method"], "none")

        # A second login reuses the registered client.
        def again(url: str) -> None:
            back = self.authorize(url)
            threading.Thread(target=lambda: urllib.request.urlopen(back).read(), daemon=True).start()

        r, w = os.pipe()
        with open(r) as stdin, open(w, "w"):
            library.login(self.fake.url, open_browser=again, stdin=stdin, out=io.StringIO())
        self.assertEqual(len(self.fake.registered), 1)

    def test_the_redirected_address_can_be_pasted(self) -> None:
        r, w = os.pipe()
        paste = open(w, "w")

        def browser(url: str) -> None:  # the browser is on another machine
            paste.write("not it\n" + self.authorize(url) + "\n")
            paste.flush()

        out = io.StringIO()
        with open(r) as stdin:
            tokens = library.login(self.fake.url, open_browser=browser, stdin=stdin, out=out)
        paste.close()
        self.assertEqual(tokens["access_token"], "good")
        self.assertIn("paste", out.getvalue())


# --- where --------------------------------------------------------------------


class WhereTest(LedgerBase):
    def test_default_is_private_and_consent_not_asked(self) -> None:
        code, out, _ = self.run_cli("where")
        self.assertEqual(code, 0)
        self.assertIn("your private library", out)
        self.assertIn("not asked yet", out)
        self.assertIn("claims.py login", out)

    def test_consent_and_place_are_kept_in_the_repository(self) -> None:
        self.sign_in()
        code, out, _ = self.run_cli("where")
        self.assertIn(TEAM, out)
        self.assertIn("Transport", out)
        self.run_cli("where", "--consent", "yes", "--labbook", TEAM_BOOK[:8])
        config = json.loads((self.repo / ".berry" / "config.json").read_text())
        self.assertEqual(config["publish"], {"consent": True, "space_id": TEAM,
                                             "labbook_id": TEAM_BOOK, "private": True})
        # Back to the private library: the team's labbook no longer fits.
        self.run_cli("where", "--private")
        config = json.loads((self.repo / ".berry" / "config.json").read_text())
        self.assertEqual(config["publish"], {"consent": True, "space_id": None,
                                             "labbook_id": None, "private": True})

    def test_an_unknown_space_is_refused(self) -> None:
        self.sign_in()
        code, _, err = self.run_cli("where", "--space", "deadbeef-0000")
        self.assertEqual(code, 2)
        self.assertIn("does not name one of your spaces", err)


# --- publish ------------------------------------------------------------------


class PublishTest(LedgerBase):
    def test_without_consent_nothing_is_sent(self) -> None:
        self.sign_in()
        cid = self.sealed("A")
        code, _, err = self.run_cli("publish", cid)
        self.assertEqual(code, 2)
        self.assertIn("--consent yes", err)
        self.assertEqual(self.fake.posts, [])
        code, out, _ = self.run_cli("publish", cid, "--yes")
        self.assertEqual(code, 0, out)

    def test_not_signed_in_is_one_line(self) -> None:
        self.consent()
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 2)
        self.assertEqual(err.strip().count("\n"), 0)
        self.assertIn("run `claims.py login`", err)

    def test_201_is_verified_and_recorded(self) -> None:
        self.sign_in()
        self.consent()
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        sent = self.fake.posts[0]
        self.assertEqual(sent["client_key"], f"ledger:github.com/lab/proj/{cid}")
        self.assertIs(sent["private"], True)
        lib = self.load(cid)["library"]
        self.assertIn(lib["id"], self.fake.claims)
        self.assertEqual(lib["url"], f"https://berry.test/library/{lib['id']}")
        self.assertEqual(lib["visibility"], "private")
        self.assertEqual(out.strip(), f"{cid}: published, private -> {lib['url']}")
        # Published already: named again, nothing is sent.
        code, out, _ = self.run_cli("publish", cid)
        self.assertEqual(len(self.fake.posts), 1)
        self.assertIn("already in the Library", out)

    def test_a_lost_answer_is_retried_with_the_same_key(self) -> None:
        self.sign_in()
        self.consent()
        cid = self.sealed("A")
        self.fake.drop_posts = 1
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.fake.claims), 1)
        self.assertTrue(self.load(cid)["library"]["id"])

    def test_200_a_claim_published_before_is_recognised(self) -> None:
        self.sign_in()
        self.consent()
        cid = self.sealed("A")
        self.run_cli("publish", cid)
        first = self.load(cid)["library"]["id"]
        claim = self.load(cid)
        claim["library"] = None  # the recording was lost
        (self.root / cid / "claim.json").write_text(json.dumps(claim, indent=2))
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        self.assertIn("already published", out)
        self.assertEqual(self.load(cid)["library"]["id"], first)
        self.assertEqual(len(self.fake.claims), 1)

    def test_409_records_nothing(self) -> None:
        self.sign_in()
        self.consent()
        cid = self.sealed("A")
        self.fake.keys[f"ledger:github.com/lab/proj/{cid}"] = ("other content", "x")
        code, out, _ = self.run_cli("publish", cid)
        self.assertEqual(code, 2)
        self.assertIn("refused (409)", out)
        self.assertIsNone(self.load(cid).get("library"))

    def test_a_copy_that_differs_is_caught_and_not_recorded(self) -> None:
        self.sign_in()
        self.consent()
        cid = self.sealed("A")

        def tamper(detail: dict) -> None:
            detail["statement"] = "The residual is 13.1 um."
            detail["evidence"][1]["caption"] = "Something else"

        self.fake.tamper = tamper
        code, out, _ = self.run_cli("publish", cid)
        self.assertEqual(code, 2)
        self.assertIn("differs from what was sent; nothing recorded", out)
        self.assertIn("statement: sent 'The residual is 31.1 um.', got 'The residual is 13.1 um.'", out)
        self.assertIn("evidence 2 caption", out)
        self.assertIsNone(self.load(cid).get("library"))

    def test_a_401_refreshes_once_and_retries(self) -> None:
        self.sign_in(access="stale")
        self.consent()
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.fake.refreshes, 1)
        tokens = library.credentials_for(self.fake.url)["tokens"]
        self.assertEqual((tokens["access_token"], tokens["refresh_token"]), ("fresh", "r2"))

    def test_an_expired_token_is_refreshed_before_asking(self) -> None:
        self.sign_in(access="stale", expires_at=1)
        self.consent()
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.fake.refreshes, 1)

    def test_cited_claims_go_first(self) -> None:
        self.sign_in()
        self.consent()
        base = self.sealed("Base")
        top = self.sealed("Top", citations=[{"local": base, "relation": "uses", "reason": "the baseline"}])
        code, out, err = self.run_cli("publish", top)
        self.assertEqual(code, 0, out + err)
        self.assertEqual([p["title"] for p in self.fake.posts], ["Base", "Top"])
        base_id = self.load(base)["library"]["id"]
        self.assertEqual(self.fake.posts[1]["citations"][0]["claim_id"], base_id)
        self.assertEqual([line.split(":")[0] for line in out.splitlines()], [base, top])

    def test_ready_publishes_every_sealed_claim_and_no_draft(self) -> None:
        self.sign_in()
        self.consent()
        a = self.sealed("A")
        b = self.sealed("B")
        self.run_cli("new", "Draft")
        code, out, err = self.run_cli("publish", "--ready")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sorted(p["title"] for p in self.fake.posts), ["A", "B"])
        self.assertTrue(self.load(a)["library"] and self.load(b)["library"])
        code, out, _ = self.run_cli("publish", "--ready")
        self.assertIn("Nothing to publish", out)

    def test_the_place_comes_from_the_config(self) -> None:
        self.sign_in()
        self.run_cli("where", "--consent", "yes", "--labbook", TEAM_BOOK)
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        sent = self.fake.posts[0]
        self.assertEqual((sent["space_id"], sent["labbook_id"]), (TEAM, TEAM_BOOK))
        self.assertNotIn("private", sent)

    def test_public_only_when_the_config_says_so_by_hand(self) -> None:
        self.sign_in()
        self.consent()
        config = json.loads((self.repo / ".berry" / "config.json").read_text())
        config["publish"]["private"] = False
        (self.repo / ".berry" / "config.json").write_text(json.dumps(config))
        cid = self.sealed("A")
        code, out, err = self.run_cli("publish", cid)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("private", self.fake.posts[0])
        self.assertEqual(self.load(cid)["library"]["visibility"], "public")


if __name__ == "__main__":
    unittest.main()
