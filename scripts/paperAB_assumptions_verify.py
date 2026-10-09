"""Check the literature support of every assumed value (paper/paperAB/assumption_support.json).

For each source with a quote, the full text is fetched from the URL given, reduced to lower-case letters and digits
(so XML tags, PDF line breaks, superscripts and spacing do not matter), and the quote must appear in it. The SHA-256
of the fetched bytes and the date are written to paper/paperAB/assumption_support_verified.json. Full texts are cached
outside the repository (licences differ), only the quotes are kept. A missing quote stops the script.
Each DOI is also resolved at OpenAlex and its title recorded.
  python scripts/paperAB_assumptions_verify.py [--refresh]
"""
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
P = REPO / "paper" / "paperAB"
CACHE = Path(os.environ.get("PERODESIGN_FT_CACHE", Path(os.environ.get("TMPDIR", REPO / ".cache")) / "perodesign_fulltext"))
MAIL = os.environ.get("PERODESIGN_CONTACT_EMAIL", "research@example.org")  # polite-pool contact for OpenAlex
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("µ", "u").replace("μ", "u")
    return re.sub(r"[^a-z0-9]", "", s)


def fetch(url, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    c = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if c.exists() and not refresh:
        return c.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            c.write_bytes(data)
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise SystemExit(f"fetch failed {url}: {last}")


def text_of(data):
    if data[:5] == b"%PDF-":
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as d:
            return " ".join(p.get_text() for p in d)
    t = data.decode("utf-8", errors="replace")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#8722;", "-"), ("&nbsp;", " ")):
        t = t.replace(a, b)
    return t


def openalex_title(doi):
    url = f"https://api.openalex.org/works/https://doi.org/{doi}?mailto={MAIL}"
    req = urllib.request.Request(url, headers={"User-Agent": f"PEROdesign/0.1 (mailto:{MAIL})"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                w = json.loads(r.read().decode("utf-8"))
            return w["title"], w["publication_year"]
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    raise SystemExit(f"OpenAlex does not resolve {doi}")


def main():
    refresh = "--refresh" in sys.argv
    spec = json.loads((P / "assumption_support.json").read_text(encoding="utf-8"))
    out, fails = {}, []
    for sid, s in spec["sources"].items():
        rec = {"cite": s.get("cite"), "doi": s.get("doi"), "url": s.get("url"), "fulltext_url": s.get("fulltext_url")}
        if s.get("doi"):
            rec["openalex_title"], rec["openalex_year"] = openalex_title(s["doi"])
            time.sleep(0.2)
        if s.get("quotes"):
            if s.get("local_file"):                      # pages that refuse scripted access: a saved copy in data/sources
                data = (REPO / s["local_file"]).read_bytes()
                if s["url"] not in data.decode("utf-8", errors="replace")[:1500]:
                    fails.append(f"{sid}: {s['local_file']} header does not name {s['url']}")
            else:
                data = fetch(s["fulltext_url"], refresh)
            body = norm(text_of(data))
            rec["sha256"] = hashlib.sha256(data).hexdigest()
            rec["bytes"] = len(data)
            rec["quotes"] = []
            for q in s["quotes"]:
                ok = norm(q) in body
                rec["quotes"].append({"quote": q, "found": ok})
                if not ok:
                    fails.append(f"{sid}: quote not found: {q[:90]!r}")
        rec["checked"] = time.strftime("%Y-%m-%d")
        out[sid] = rec
    used = {r for row in spec["rows"] for r in row.get("support", [])}
    missing = sorted(used - set(spec["sources"]))
    if missing:
        fails.append(f"rows cite unknown sources {missing}")
    for row in spec["rows"]:
        if row["status"] not in ("sourced", "derived", "assumed", "design choice", "convention", "proxy"):
            fails.append(f"{row['id']}: bad status {row['status']}")
        if not row.get("support") and row["status"] != "design choice":
            fails.append(f"{row['id']}: no support given")
    (P / "assumption_support_verified.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    nq = sum(len(r.get("quotes", [])) for r in out.values())
    print(json.dumps({"sources": len(out), "quotes": nq, "rows": len(spec["rows"]), "fail": fails}, indent=1))
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
