"""Keyed OpenAlex access for the reference and assumption checks.

The key is read from OPENALEX_API_KEY (environment first, then the git-ignored .env at the repository root) and is
appended ONLY to requests for api.openalex.org: Crossref, doi.org and publisher pages never see it, and it is removed
from any error text. Without a key, requests fall into OpenAlex's anonymous budget, which is shared by every user on
the same IP address and runs out; a 429 from OpenAlex therefore stops the script with an explanation instead of being
retried.
"""
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOST = "api.openalex.org"


def _read_key():
    k = os.environ.get("OPENALEX_API_KEY", "").strip()
    if k:
        return k
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENALEX_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


KEY = _read_key()
_warned = False


class OpenAlexBudgetError(SystemExit):
    """OpenAlex refused for budget (HTTP 429). Not an Exception subclass, so callers' retry loops do not swallow it."""


def is_openalex(url):
    return urllib.parse.urlsplit(url).hostname == HOST


def keyed(url, key=None):
    """Return url with api_key appended if, and only if, the host is api.openalex.org and a key is set."""
    key = KEY if key is None else key
    if not key or not is_openalex(url):
        return url
    p = urllib.parse.urlsplit(url)
    q = [(a, b) for a, b in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if a != "api_key"]
    return urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(q + [("api_key", key)])))


def redact(text, key=None):
    key = KEY if key is None else key
    return text.replace(key, "<OPENALEX_API_KEY>") if key else text


def fetch(url, headers=None, timeout=40):
    """GET url and return the body bytes. OpenAlex requests carry the key; a 429 from OpenAlex raises
    OpenAlexBudgetError with the server's reason."""
    global _warned
    if is_openalex(url) and not KEY and not _warned:
        print("OpenAlex: no OPENALEX_API_KEY set; using the shared anonymous budget of this IP address",
              file=sys.stderr)
        _warned = True
    req = urllib.request.Request(keyed(url), headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429 and is_openalex(url):
            body = redact(e.read()[:300].decode("utf-8", errors="replace"))
            raise OpenAlexBudgetError(
                f"OpenAlex refused (HTTP 429), key sent: {'yes' if KEY else 'no'}. Server says: {body}\n"
                "Set OPENALEX_API_KEY (environment or the repository .env) to use your own budget.") from None
        raise
