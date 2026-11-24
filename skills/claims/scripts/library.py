"""The Berry Science Library over HTTP: sign in, and publish sealed claims.

    claims.py login              sign in to berry.science (OAuth, in the browser)
    claims.py logout             forget this machine's sign-in
    claims.py where              where this project publishes; the consent
    claims.py publish <id>...    publish sealed claims, each read back and compared

`publish` sends each claim from the ledger straight to the Library's API, so
no claim passes through an agent's context on its way there: the agent runs
one command and reads one line per claim. Each claim is sent with a
`client_key` naming it ("ledger:<repository>/<claim id>"), so a retry after a
lost answer returns the claim already published instead of a second copy.
After publishing, the claim is read back and compared field by field with
what was sent; only a match is recorded in the ledger.

Sign-in is OAuth 2.0 with PKCE against the authorization server the API names
(RFC 9728, then RFC 8414). The client registers itself once per API
(dynamic registration, a public client) and keeps its tokens in
$XDG_CONFIG_HOME/berry/credentials.json (~/.config/berry/...), mode 0600,
keyed by the API's URL. BERRY_API_URL points everything at another API.

Where a project publishes is kept in `.berry/config.json` at the top of the
repository, beside `claims/`:

    {"publish": {"consent": true, "space_id": null, "labbook_id": null, "private": true}}

Imported by claims.py, which registers the commands (`add_commands`) and is
passed in as `host`: its ledger functions build what is sent, and its
`LedgerError` is how a command here refuses.

Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import hashlib
import http.client
import http.server
import io
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

DEFAULT_API = "https://api.berry.science"
CLIENT_NAME = "Berry claims.py"
# The loopback redirect is registered with fixed ports: the authorization
# server matches redirect URIs exactly, port included. The first free one is
# used; with none free, the redirected address is pasted instead.
LOOPBACK_PORTS = (53781, 53782, 53783)
# Seconds to wait before each retry of a request that did not get an answer
# (or got a 502/503/504). Retrying a publish is safe: same client_key.
RETRY_DELAYS: tuple[float, ...] = (1.0, 3.0, 9.0)
TIMEOUT = 60
LOGIN_TIMEOUT = 600
EARLY_REFRESH = 60  # refresh a token this many seconds before it expires
NETWORK_ERRORS = (OSError, http.client.HTTPException)  # URLError is an OSError


class LibraryError(Exception):
    """A command that cannot go ahead, said in a sentence."""


class NotLoggedIn(LibraryError):
    pass


def api_url() -> str:
    """The API: api.berry.science, or BERRY_API_URL (a local or test one)."""
    return (os.environ.get("BERRY_API_URL") or DEFAULT_API).rstrip("/")


def login_hint(api: str) -> str:
    return f"Not signed in to {api}: run `claims.py login` (in a terminal; it opens the browser)."


# --- PKCE (RFC 7636) ----------------------------------------------------------


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def code_challenge(verifier: str) -> str:
    """S256: BASE64URL(SHA256(verifier)), unpadded."""
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def pkce_pair() -> tuple[str, str]:
    """(verifier, challenge). 32 random bytes make a 43-character verifier."""
    verifier = b64url(secrets.token_bytes(32))
    return verifier, code_challenge(verifier)


# --- the credentials file -----------------------------------------------------


def credentials_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "berry" / "credentials.json"


def load_credentials() -> dict[str, Any]:
    path = credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryError(f"cannot read {path}: {exc}")
    return data if isinstance(data, dict) else {}


def save_credentials(data: dict[str, Any]) -> None:
    """Written whole, to a file only its owner can read, then moved into place."""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def credentials_for(api: str) -> dict[str, Any]:
    return load_credentials().get(api) or {}


def update_credentials(api: str, **fields: Any) -> None:
    data = load_credentials()
    entry = data.setdefault(api, {})
    for key, value in fields.items():
        if value is None:
            entry.pop(key, None)
        else:
            entry[key] = value
    save_credentials(data)


# --- HTTP ---------------------------------------------------------------------


def _parse(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"detail": raw.decode("utf-8", "replace")[:500]}


def http_json(
    method: str,
    url: str,
    *,
    body: Any = None,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """(status, parsed body) for any HTTP status. Raises only when no answer came."""
    h = {"Accept": "application/json", "User-Agent": "berry-claims.py"}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("ascii")
        h["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse(exc.read())


def with_retries(fn: Callable[[], tuple[int, Any]], what: str) -> tuple[int, Any]:
    delays = RETRY_DELAYS
    for attempt in range(len(delays) + 1):
        try:
            status, data = fn()
        except NETWORK_ERRORS as exc:
            if attempt == len(delays):
                raise LibraryError(f"no answer from {what} after {attempt + 1} tries: {exc}")
            time.sleep(delays[attempt])
            continue
        if status in (502, 503, 504) and attempt < len(delays):
            time.sleep(delays[attempt])
            continue
        return status, data
    raise AssertionError("unreachable")


def detail_of(body: Any) -> str:
    """The server's reason, in one line."""
    if isinstance(body, dict):
        d = body.get("detail") or body.get("error_description") or body.get("error") or body.get("msg")
        if isinstance(d, list):  # a validation error: [{loc, msg}, ...]
            d = "; ".join(
                f"{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg')}"
                if isinstance(e, dict) else str(e)
                for e in d
            )
        if d:
            return " ".join(str(d).split())[:600]
    return " ".join(str(body).split())[:300] if body else "no reason given"


# --- discovery and registration -----------------------------------------------


def discover(api: str) -> dict[str, Any]:
    """The authorization server's metadata, found from the API's RFC 9728
    protected-resource metadata. The API is an MCP server at <api>/mcp, so the
    metadata is at /.well-known/oauth-protected-resource/mcp."""
    issuer = None
    for path in ("/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"):
        status, meta = with_retries(lambda: http_json("GET", api + path), api)
        if status == 200 and isinstance(meta, dict) and meta.get("authorization_servers"):
            issuer = str(meta["authorization_servers"][0]).rstrip("/")
            break
    if not issuer:
        raise LibraryError(f"{api} does not say where to sign in (no protected-resource metadata)")
    parts = urllib.parse.urlsplit(issuer)
    for url in (
        issuer + "/.well-known/oauth-authorization-server",  # where Supabase serves it
        f"{parts.scheme}://{parts.netloc}/.well-known/oauth-authorization-server{parts.path}",
        issuer + "/.well-known/openid-configuration",
    ):
        status, meta = with_retries(lambda: http_json("GET", url), issuer)
        if (
            status == 200
            and isinstance(meta, dict)
            and meta.get("authorization_endpoint")
            and meta.get("token_endpoint")
        ):
            meta.setdefault("issuer", issuer)
            return meta
    raise LibraryError(f"no OAuth metadata at {issuer}")


def register(meta: dict[str, Any], redirect_uris: list[str]) -> dict[str, Any]:
    """Register this script as a public client (RFC 7591); what to keep of it."""
    endpoint = meta.get("registration_endpoint")
    if not endpoint:
        raise LibraryError(f"{meta.get('issuer')} does not register clients")
    request = {
        "client_name": CLIENT_NAME,
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    status, body = with_retries(lambda: http_json("POST", endpoint, body=request), endpoint)
    if status not in (200, 201) or not isinstance(body, dict) or not body.get("client_id"):
        raise LibraryError(f"registering with {meta.get('issuer')} was refused ({status}): {detail_of(body)}")
    return {
        "client_id": body["client_id"],
        "redirect_uris": body.get("redirect_uris") or redirect_uris,
        "issuer": meta.get("issuer"),
        "authorization_endpoint": meta["authorization_endpoint"],
        "token_endpoint": meta["token_endpoint"],
    }


def token_record(body: dict[str, Any], old: dict[str, Any] | None = None) -> dict[str, Any]:
    expires_in = body.get("expires_in")
    record = {
        "access_token": body["access_token"],
        # A refresh may or may not rotate the refresh token.
        "refresh_token": body.get("refresh_token") or (old or {}).get("refresh_token"),
        "expires_at": int(time.time() + float(expires_in)) if expires_in else None,
    }
    return {k: v for k, v in record.items() if v is not None}


# --- login --------------------------------------------------------------------


class _Callback(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if urllib.parse.urlsplit(self.path).path != "/callback":
            self.send_error(404)
            return
        self.server.results.put(("loopback", self.path))  # type: ignore[attr-defined]
        page = (
            "<!doctype html><meta charset=utf-8><title>Berry</title>"
            "<p style='font:16px system-ui;margin:3em'>Signed in. "
            "You can close this tab and go back to the terminal.</p>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args: Any) -> None:
        pass


def bind_loopback(redirect_uris: list[str]) -> tuple[http.server.HTTPServer | None, str]:
    """A server on the first registered port that is free, and its redirect
    URI. None when none is: the redirected address is then pasted."""
    for uri in redirect_uris:
        port = urllib.parse.urlsplit(uri).port
        if not port:
            continue
        try:
            return http.server.HTTPServer(("127.0.0.1", port), _Callback), uri
        except OSError:
            continue
    return None, redirect_uris[0]


def code_from_redirect(text: str, state: str) -> str:
    """The authorization code in a redirected address (or just its query)."""
    text = text.strip()
    query = urllib.parse.urlsplit(text).query if "?" in text else text
    params = urllib.parse.parse_qs(query)
    first = {k: v[0] for k, v in params.items()}
    if "error" in first:
        why = first.get("error_description") or first["error"]
        raise LibraryError(f"sign-in was refused: {why}")
    if first.get("state") != state:
        raise LibraryError(
            "that address belongs to another sign-in (its state differs): "
            "run `claims.py login` again and use the newest link"
        )
    if not first.get("code"):
        raise LibraryError("no authorization code in that address")
    return first["code"]


def login(
    api: str,
    *,
    open_browser: Callable[[str], Any] = webbrowser.open,
    stdin: Any = None,
    out: Any = None,
) -> dict[str, Any]:
    """Sign in through the browser; returns and stores the tokens."""
    stdin = sys.stdin if stdin is None else stdin
    out = sys.stdout if out is None else out
    client = credentials_for(api).get("client")
    if not client:
        meta = discover(api)
        client = register(meta, [f"http://127.0.0.1:{p}/callback" for p in LOOPBACK_PORTS])
        update_credentials(api, client=client)

    server, redirect_uri = bind_loopback(client["redirect_uris"])
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = client["authorization_endpoint"] + "?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    print("Sign in to berry.science and approve claims.py at:\n", file=out)
    print(f"  {url}\n", file=out)
    print(
        "If the browser cannot reach this machine (an ssh or tmux session), the "
        "page it ends on will not load: copy that page's address and paste it here.",
        file=out,
        flush=True,
    )

    results: queue.Queue[tuple[str, str]] = queue.Queue()
    if server is not None:
        server.results = results  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def read_pasted() -> None:
        while True:
            try:
                line = stdin.readline()
            except (OSError, ValueError):
                return
            if not line:
                return
            if "code=" in line or "error=" in line:
                results.put(("pasted", line))
                return
            if line.strip():
                print("That is not the address the browser ended on; paste the whole of it.", file=out, flush=True)

    threading.Thread(target=read_pasted, daemon=True).start()
    with contextlib.suppress(Exception):
        open_browser(url)
    try:
        _, address = results.get(timeout=LOGIN_TIMEOUT)
    except queue.Empty:
        raise LibraryError(f"no sign-in arrived within {LOGIN_TIMEOUT // 60} minutes; run `claims.py login` again")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    code = code_from_redirect(address, state)

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client["client_id"],
        "code_verifier": verifier,
    }
    status, body = with_retries(lambda: http_json("POST", client["token_endpoint"], form=form), client["token_endpoint"])
    if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
        raise LibraryError(f"the sign-in could not be completed ({status}): {detail_of(body)}")
    tokens = token_record(body)
    update_credentials(api, tokens=tokens)
    return tokens


# --- an authorized session ----------------------------------------------------


class Session:
    """Calls to the API with the stored token: refreshed when it has expired,
    and once more on a 401."""

    def __init__(self, api: str | None = None):
        self.api = api or api_url()
        entry = credentials_for(self.api)
        self.client = entry.get("client") or {}
        self.tokens = entry.get("tokens") or {}
        if not self.tokens.get("access_token"):
            raise NotLoggedIn(login_hint(self.api))

    def refresh(self) -> None:
        refresh_token = self.tokens.get("refresh_token")
        endpoint = self.client.get("token_endpoint")
        if not (refresh_token and endpoint and self.client.get("client_id")):
            raise NotLoggedIn(f"The sign-in to {self.api} has expired: run `claims.py login`.")
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client["client_id"],
        }
        status, body = with_retries(lambda: http_json("POST", endpoint, form=form), endpoint)
        if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
            raise NotLoggedIn(f"The sign-in to {self.api} has expired: run `claims.py login`.")
        self.tokens = token_record(body, self.tokens)
        update_credentials(self.api, tokens=self.tokens)

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        expires_at = self.tokens.get("expires_at")
        if expires_at and expires_at - EARLY_REFRESH < time.time():
            self.refresh()
        refreshed = False
        while True:
            status, data = with_retries(
                lambda: http_json(
                    method,
                    self.api + path,
                    body=body,
                    headers={"Authorization": f"Bearer {self.tokens['access_token']}"},
                ),
                self.api,
            )
            if status == 401 and not refreshed:
                self.refresh()
                refreshed = True
                continue
            if status == 401:
                raise NotLoggedIn(f"{self.api} does not accept this sign-in: run `claims.py login`.")
            return status, data

    def get(self, path: str) -> Any:
        status, data = self.call("GET", path)
        if status != 200:
            raise LibraryError(f"GET {path}: {status} {detail_of(data)}")
        return data


# --- where this project publishes ---------------------------------------------

PUBLISH_DEFAULTS: dict[str, Any] = {"consent": None, "space_id": None, "labbook_id": None, "private": True}


def config_path(repo: Path) -> Path:
    return repo / ".berry" / "config.json"


def load_config(repo: Path) -> dict[str, Any]:
    path = config_path(repo)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LibraryError(f"{path} is not valid JSON: {exc}")
    return data if isinstance(data, dict) else {}


def publish_config(repo: Path) -> dict[str, Any]:
    return {**PUBLISH_DEFAULTS, **(load_config(repo).get("publish") or {})}


def save_publish_config(repo: Path, publish: dict[str, Any]) -> None:
    data = load_config(repo)
    data["publish"] = publish
    path = config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalise_remote(url: str) -> str:
    """A remote URL as host/path, lower-cased, whatever the protocol:
    git@github.com:a/b.git, https://user@github.com/a/b and ssh://… all give
    github.com/a/b. A local path gives its last name only."""
    url = url.strip()
    scp = re.match(r"^(?:[^@/\s]+@)?([\w.-]+):(?!//)(.+)$", url)
    if "://" in url:
        parts = urllib.parse.urlsplit(url)
        host, path = parts.hostname or "", parts.path
    elif scp and len(scp.group(1)) > 1:  # not a Windows drive letter
        host, path = scp.group(1), scp.group(2)
    else:
        host, path = "", url
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    path = path.rstrip("/")
    if not host:
        return Path(path).name.lower()
    return f"{host}/{path}".lower()


def repo_identity(repo: Path, git: Callable[..., str | None]) -> str:
    """The origin remote, normalised; else the repository folder's name.

    `repo` is the project root, which for a project in a subfolder of a
    repository holding several (claims/ below the git toplevel) is not the
    toplevel: its path inside the repository is added, so two projects of
    one repository never share a key for claims of the same id.
    """
    remote = git("remote", "get-url", "origin", cwd=repo)
    top = git("rev-parse", "--show-toplevel", cwd=repo)
    name = normalise_remote(remote) if remote else ""
    if not name:
        name = (Path(top) if top else repo).resolve().name.lower()
    if top:
        inside = repo.resolve().relative_to(Path(top).resolve()).as_posix()
        if inside not in ("", "."):
            name = f"{name}/{inside}"
    return name


def client_key(repo_id: str, claim_id: str) -> str:
    key = f"ledger:{repo_id}/{claim_id}"
    if len(key) > 200:  # the Library's limit
        key = f"ledger:{hashlib.sha256(repo_id.encode()).hexdigest()[:20]}/{claim_id}"
    return key


# --- comparing what came back with what was sent ------------------------------


def _short(value: Any) -> str:
    """A value for a difference line: never a whole evidence file."""
    if isinstance(value, str):
        return repr(value) if len(value) <= 60 else f"{len(value)} characters"
    return repr(value)


def _first_difference(a: str, b: str) -> str:
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"sent {len(a)} characters, got {len(b)}; first difference at character {n}"


def differences(sent: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """What the Library holds that differs from what was sent, one line each."""
    found: list[str] = []

    def norm(v: Any) -> Any:
        return None if v in ("", None) else v

    def same(where: str, a: Any, b: Any) -> None:
        a, b = norm(a), norm(b)
        if a == b:
            return
        if isinstance(a, str) and isinstance(b, str) and max(len(a), len(b)) > 60:
            found.append(f"{where}: {_first_difference(a, b)}")
        else:
            found.append(f"{where}: sent {_short(a)}, got {_short(b)}")

    def lower(v: Any) -> Any:
        return str(v).lower() if v else None

    for field in ("title", "statement", "claim_type", "holds_when"):
        same(field, sent.get(field), got.get(field))

    evidence = sorted(
        (e for e in got.get("evidence") or [] if not e.get("deleted_at")),
        key=lambda e: e.get("ordinal", 0),
    )
    if len(evidence) != len(sent.get("evidence") or []):
        found.append(f"evidence: sent {len(sent.get('evidence') or [])} items, got {len(evidence)}")
    for n, (s, g) in enumerate(zip(sent.get("evidence") or [], evidence), start=1):
        same(f"evidence {n} kind", s.get("kind"), g.get("kind"))
        same(f"evidence {n} content", s.get("content"), g.get("content"))
        same(f"evidence {n} caption", s.get("caption"), g.get("caption"))
        same(f"evidence {n} format", s.get("format") or "plain", g.get("format"))
        same(f"evidence {n} language", s.get("language"), g.get("language"))

    citations = sorted(got.get("citations") or [], key=lambda c: c.get("ordinal", 0))
    if len(citations) != len(sent.get("citations") or []):
        found.append(f"citations: sent {len(sent.get('citations') or [])}, got {len(citations)}")
    for n, (s, g) in enumerate(zip(sent.get("citations") or [], citations), start=1):
        same(f"citation [{n}] claim", lower(s.get("claim_id")), lower(g.get("cited_claim_id")))
        same(f"citation [{n}] external", s.get("external"), g.get("external"))
        same(f"citation [{n}] relation", s.get("relation") or "cites", g.get("relation"))
        for field in ("locator", "reason", "label"):
            same(f"citation [{n}] {field}", s.get(field), g.get(field))
        same(f"citation [{n}] source review", lower(s.get("source_review_id")), lower(g.get("source_review_id")))

    def conventions(items: Any) -> dict[str, tuple[Any, Any, Any]]:
        return {c.get("key"): (c.get("version"), c.get("statement"), norm(c.get("category"))) for c in items or []}

    sent_conv, got_conv = conventions(sent.get("conventions")), conventions(got.get("conventions"))
    for key in sorted(set(sent_conv) | set(got_conv), key=str):
        if sent_conv.get(key) != got_conv.get(key):
            if key not in got_conv:
                found.append(f"convention {key}: sent, not in the Library's copy")
            elif key not in sent_conv:
                found.append(f"convention {key}: in the Library's copy, not sent")
            else:
                found.append(f"convention {key}: version, statement or category differs")

    wanted = "private" if sent.get("private") or sent.get("space_id") else "public"
    if got.get("visibility") != wanted:
        found.append(f"visibility: wanted {wanted}, got {_short(got.get('visibility'))}")
    if sent.get("space_id"):
        same("space", lower(sent["space_id"]), lower(got.get("space_id")))
    if sent.get("labbook_id"):
        same("labbook", lower(sent["labbook_id"]), lower(got.get("labbook_id")))
    return found


# --- publishing ---------------------------------------------------------------


class Stop(Exception):
    """Publishing stops here; the message has been printed."""


def post_and_read_back(
    session: Session, path: str, payload: dict[str, Any], read_path: str
) -> tuple[str, int, dict[str, Any]]:
    """POST `payload` to `path`, then GET `read_path` + its id: (id, the
    POST's status, the copy read back). 201 is new; 200 is a retry the
    Library recognised by the client_key; 409 is that key with other content.

    Everything the ledger publishes goes through here: claims, and source
    reviews through POST /source-reviews with GET /source-reviews/<id>."""
    status, body = session.call("POST", path, payload)
    if status not in (200, 201) or not isinstance(body, dict) or not body.get("id"):
        raise LibraryError(f"refused ({status}): {detail_of(body)}")
    library_id = str(body["id"])
    read_status, got = session.call("GET", f"{read_path}/{library_id}")
    if read_status != 200 or not isinstance(got, dict):
        raise LibraryError(
            f"published as {library_id}, but reading it back failed ({read_status}): "
            f"{detail_of(got)}. Nothing recorded; run publish again to verify it"
        )
    return library_id, status, got


def publish_claim(
    host: ModuleType, ledger: Any, session: Session, cid: str, place: dict[str, Any], repo_id: str
) -> str:
    """Publish one sealed claim; its line of output."""
    # Public only when the config says "private": false, set by hand: `where`
    # offers no switch for it.
    public = place.get("private") is False and not place.get("space_id")
    payload = host.claim_payload(
        ledger, argparse.Namespace(id=cid, space_id=place.get("space_id"), public=public)
    )
    if place.get("labbook_id"):
        payload["labbook_id"] = place["labbook_id"]
    payload["client_key"] = client_key(repo_id, cid)

    library_id, status, got = post_and_read_back(session, "/claims", payload, "/claims")
    diffs = differences(payload, got)
    if diffs:
        lines = "\n".join(f"    {d}" for d in diffs)
        raise LibraryError(
            f"the Library's copy ({library_id}) differs from what was sent; nothing recorded:\n{lines}"
        )
    with contextlib.redirect_stdout(io.StringIO()):  # it prints its own line
        host.cmd_published(
            ledger, argparse.Namespace(id=cid, library_id=library_id, visibility=got["visibility"])
        )
    url = ledger.load(cid)["library"]["url"]
    how = "published" if status == 201 else "was already published (same key), verified"
    return f"{cid}: {how}, {got['visibility']} -> {url}"


def review_differences(sent: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """What the Library's copy of a source review holds that differs from
    what was sent. The paper's key is left out: the Library normalises it
    (`arXiv:2502.09437v2` and `arxiv:2502.09437v2` are one paper)."""
    found: list[str] = []

    def norm(v: Any) -> Any:
        return None if v in ("", None, []) else v

    def same(where: str, a: Any, b: Any) -> None:
        a, b = norm(a), norm(b)
        if a == b:
            return
        if isinstance(a, str) and isinstance(b, str) and max(len(a), len(b)) > 60:
            found.append(f"{where}: {_first_difference(a, b)}")
        else:
            found.append(f"{where}: sent {_short(a)}, got {_short(b)}")

    for field in (
        "read_from", "verdict", "summary", "source_version",
        "locator", "quote", "purpose", "method",
    ):
        same(field, sent.get(field), got.get(field))
    items = sorted(
        (i for i in got.get("items") or [] if not i.get("deleted_at")),
        key=lambda i: i.get("ordinal", 0),
    )
    if len(items) != len(sent.get("items") or []):
        found.append(f"items: sent {len(sent.get('items') or [])}, got {len(items)}")
    for n, (s, g) in enumerate(zip(sent.get("items") or [], items), start=1):
        for field in ("quote", "body", "severity", "proposed_fix"):
            same(f"item {n} {field}", s.get(field), g.get(field))
    if len(sent.get("conventions") or []) != len(got.get("conventions") or []):
        found.append(
            f"conventions: sent {len(sent.get('conventions') or [])}, "
            f"got {len(got.get('conventions') or [])}"
        )
    fix = sent.get("correction_claim_id")
    same("correction", str(fix).lower() if fix else None,
         str(got.get("correction_claim_id")).lower() if got.get("correction_claim_id") else None)
    wanted = "private" if sent.get("private") or sent.get("space_id") else "public"
    if got.get("visibility") != wanted:
        found.append(f"visibility: wanted {wanted}, got {_short(got.get('visibility'))}")
    return found


def publish_source_review(
    host: ModuleType, ledger: Any, session: Session, path: str, place: dict[str, Any], repo_id: str
) -> str:
    """Publish one source review (a `sources/…json` path); its line of output.
    The same post-and-read-back as a claim, against /source-reviews."""
    public = place.get("private") is False and not place.get("space_id")
    payload = host.source_payload(
        ledger, argparse.Namespace(path=path, space_id=place.get("space_id"), public=public)
    )
    payload["client_key"] = client_key(repo_id, path)
    library_id, status, got = post_and_read_back(
        session, "/source-reviews", payload, "/source-reviews"
    )
    diffs = review_differences(payload, got)
    if diffs:
        lines = "\n".join(f"    {d}" for d in diffs)
        raise LibraryError(
            f"the Library's copy ({library_id}) differs from what was sent; nothing recorded:\n{lines}"
        )
    with contextlib.redirect_stdout(io.StringIO()):
        host.cmd_source_published(
            ledger, argparse.Namespace(path=path, library_id=library_id, visibility=got["visibility"])
        )
    url = ledger.source_review(path)["library"]["url"]
    how = "published" if status == 201 else "was already published (same key), verified"
    return f"{path}: {how}, {got['visibility']} -> {url}"


def to_publish(host: ModuleType, ledger: Any, ids: list[str], ready: bool) -> list[str]:
    """The claims (and source reviews, as sources/ paths) to publish, in order."""
    claims = ledger.all()
    if ready:
        targets = [
            cid for cid, c in claims.items()
            if c.get("status") == "sealed" and not (c.get("library") or {}).get("id")
        ]
    else:
        targets = list(ids)
        for cid in targets:
            if cid not in claims:
                raise LibraryError(f"no claim {cid!r} in {ledger.root}")
    order: list[str] = []
    for cid in sorted(targets):
        for item in host.publish_order(claims, cid, ledger):
            if item not in order:
                order.append(item)
    return order


# --- the commands -------------------------------------------------------------


def cmd_login(host: ModuleType, ledger: Any, a: argparse.Namespace) -> int:
    api = api_url()
    login(api, open_browser=(lambda url: None) if a.no_browser else webbrowser.open)
    who = ""
    with contextlib.suppress(LibraryError):
        me = Session(api).get("/authors/me")
        if isinstance(me, dict) and me.get("display_name"):
            who = f" as {me['display_name']}"
    print(f"Signed in to {api}{who}. The sign-in is kept in {credentials_path()}.")
    return 0


def cmd_logout(host: ModuleType, ledger: Any, a: argparse.Namespace) -> int:
    api = api_url()
    if not credentials_for(api).get("tokens"):
        print(f"Not signed in to {api}.")
        return 0
    update_credentials(api, tokens=None)
    print(f"Signed out of {api}: its tokens are removed from {credentials_path()}.")
    return 0


def _pick(items: list[dict[str, Any]], given: str, what: str) -> dict[str, Any]:
    found = [i for i in items if str(i.get("id", "")).lower().startswith(given.lower())]
    if len(given) < 8 or len(found) != 1:
        raise LibraryError(
            f"{given!r} does not name one of your {what}s: give its id (at least "
            f"8 characters) as `claims.py where` lists them"
        )
    return found[0]


def describe_place(p: dict[str, Any], spaces: dict[str, str], books: dict[str, str]) -> str:
    if p.get("space_id"):
        where = f"team space {spaces.get(p['space_id'], '')} ({p['space_id']})".replace("  ", " ")
    elif p.get("private", True):
        where = "your private library"
    else:
        where = "the public Library"
    if p.get("labbook_id"):
        where += f", labbook {books.get(p['labbook_id'], '')} ({p['labbook_id']})".replace("  ", " ")
    return where


def cmd_where(host: ModuleType, ledger: Any, a: argparse.Namespace) -> int:
    repo = ledger.root.parent
    place = publish_config(repo)
    changing = a.consent or a.space or a.private or a.labbook

    spaces: list[dict[str, Any]] = []
    books: list[dict[str, Any]] = []
    session = None
    try:
        session = Session()
        spaces = session.get("/spaces") or []
        books = session.get("/labbooks") or []
    except NotLoggedIn:
        if a.space or a.labbook:
            raise
    space_names = {str(s["id"]): s.get("name", "") for s in spaces}
    book_names = {str(b["id"]): b.get("title", "") for b in books}

    if changing:
        if a.private:
            place.update(private=True, space_id=None)
        if a.space:
            space = _pick(spaces, a.space, "space")
            if space.get("personal"):
                place.update(private=True, space_id=None)
            else:
                place.update(private=True, space_id=str(space["id"]))
        if (a.private or a.space) and not a.labbook and place.get("labbook_id"):
            # A labbook in another space than the one just chosen no longer fits.
            book = next((b for b in books if str(b["id"]) == place["labbook_id"]), None)
            here = place.get("space_id") or _personal(spaces)
            if book is None or str(book.get("space_id") or "") != str(here or ""):
                place["labbook_id"] = None
                print("The labbook is no longer set: it is not in that space.")
        if a.labbook:
            if a.labbook == "none":
                place["labbook_id"] = None
            else:
                book = _pick(books, a.labbook, "labbook")
                place["labbook_id"] = str(book["id"])
                # The labbook's place is the claim's, unless the labbook is public:
                # publishing publicly is never inferred.
                book_space = str(book.get("space_id") or "")
                if book_space and book_space != _personal(spaces):
                    place.update(private=True, space_id=book_space)
                elif book_space:
                    place.update(private=True, space_id=None)
        if a.consent:
            place["consent"] = a.consent == "yes"
        save_publish_config(repo, place)

    consent = {True: "yes", False: "no", None: "not asked yet"}[place.get("consent")]
    print(f"publishes to: {describe_place(place, space_names, book_names)}")
    print(f"consent:      {consent}")
    print(f"config:       {config_path(repo)}")
    if session is None:
        print(f"\n{login_hint(api_url())} Then this lists your spaces and labbooks.")
        return 0
    if not changing:
        print("\nspaces (claims.py where --space <id>):")
        for s in spaces:
            kind = "your private library" if s.get("personal") else f"team, {s.get('role', '')}"
            print(f"  {s['id']}  {s.get('name', '')} ({kind})")
        print("\nlabbooks (claims.py where --labbook <id>):")
        if not books:
            print("  none yet")
        for b in books:
            where = b.get("space_name") or ("public" if not b.get("space_id") else "")
            print(f"  {b['id']}  {b.get('title', '')} ({where}, {b.get('claims', 0)} claims)")
    return 0


def _personal(spaces: list[dict[str, Any]]) -> str | None:
    return next((str(s["id"]) for s in spaces if s.get("personal")), None)


def cmd_publish(host: ModuleType, ledger: Any, a: argparse.Namespace) -> int:
    if not a.ids and not a.ready:
        raise LibraryError("name the claims to publish, or --ready for every sealed one not yet published")
    repo = ledger.root.parent
    place = publish_config(repo)
    if place.get("consent") is not True and not a.yes:
        raise LibraryError(
            "this project has no consent recorded for publishing. Ask the researcher "
            "once, then `claims.py where --consent yes` (or --yes for this run only)"
        )
    order = to_publish(host, ledger, a.ids, a.ready)
    claims = ledger.all()
    for cid in a.ids:  # named, but already there
        lib = claims[cid].get("library") or {}
        if lib.get("id"):
            print(f"{cid}: already in the Library, {lib.get('visibility', '?')} -> {lib.get('url')}")
    if not order:
        if a.ready:
            print("Nothing to publish: every sealed claim is in the Library.")
        return 0
    session = Session()
    repo_id = repo_identity(repo, host.git)
    for item in order:
        publish = publish_source_review if item.startswith("sources/") else publish_claim
        try:
            line = publish(host, ledger, session, item, place, repo_id)
        except host.LedgerError as exc:
            print(f"{item}: not published: {exc}")
            return 2
        except NotLoggedIn:
            raise
        except LibraryError as exc:
            print(f"{item}: {exc}")
            return 2
        print(line, flush=True)
    return 0


def _command(fn: Callable[..., int], host: ModuleType) -> Callable[[Any, argparse.Namespace], int]:
    @functools.wraps(fn)
    def run(ledger: Any, a: argparse.Namespace) -> int:
        try:
            return fn(host, ledger, a)
        except LibraryError as exc:
            raise host.LedgerError(str(exc)) from exc

    return run


def add_commands(sub: Any, host: ModuleType) -> None:
    """Register login, logout, where and publish on claims.py's subparsers."""
    s = sub.add_parser("login", help="sign in to berry.science, in the browser")
    s.add_argument("--no-browser", action="store_true", help="only print the link")
    s.set_defaults(run=_command(cmd_login, host))

    s = sub.add_parser("logout", help="forget this machine's sign-in")
    s.set_defaults(run=_command(cmd_logout, host))

    s = sub.add_parser("where", help="where this project publishes, and its consent")
    s.add_argument("--consent", choices=["yes", "no"], help="the researcher's answer, once per project")
    group = s.add_mutually_exclusive_group()
    group.add_argument("--private", action="store_true", help="into your private library (the default)")
    group.add_argument("--space", help="into this team space (its id)")
    s.add_argument("--labbook", help="file claims in this labbook (its id), or 'none'")
    s.set_defaults(run=_command(cmd_where, host))

    s = sub.add_parser("publish", help="publish sealed claims, verified by reading them back")
    s.add_argument("ids", nargs="*", help="claims to publish, with what they rest on")
    s.add_argument("--ready", action="store_true", help="every sealed claim not yet published")
    s.add_argument("--yes", action="store_true", help="publish without recorded consent, this once")
    s.set_defaults(run=_command(cmd_publish, host))
