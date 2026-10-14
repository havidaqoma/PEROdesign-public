"""G1 step 2 material-source search (docs/G1_step2_preregistration.md §2): find the ONE open-access Europe PMC paper
whose single table gives eps_r, band gap, electron affinity, Nc, Nv, mu_n, mu_p and doping for as many as possible of
Spiro-MeOTAD, TiO2, PEDOT:PSS, PCBM, BCP. Ranking = number of the 5 materials that appear as COLUMNS of one table with
all 8 property rows present; ties -> newer paper. Writes g1s2_sources.json. Failed requests -> non-zero exit.
Usage: python scripts/find_g1s2_sources.py <out dir>"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "perodesign/0.1 (mailto:" + os.environ.get("PERODESIGN_CONTACT_EMAIL", "research@example.org") + ")"}
QUERY = ('perovskite AND (SCAPS OR "drift-diffusion" OR "numerical simulation") AND ("Spiro-OMeTAD" OR "spiro-MeOTAD") '
         'AND (PCBM OR "PEDOT:PSS" OR BCP) AND "electron affinity" AND OPEN_ACCESS:y AND (LICENSE:"cc by" OR '
         'LICENSE:"cc-by" OR LICENSE:"cc by-nc")')
MATS = {"Spiro": r"spiro", "TiO2": r"\bTiO\s?2\b", "PEDOT": r"PEDOT", "PCBM": r"PC\s?\[?6?1?\]?BM|PCBM", "BCP": r"\bBCP\b"}
PROPS = {"eps": r"permittiv|dielectric", "Eg": r"band\s?gap|E\s?g\b", "chi": r"electron affinity|χ",
         "Nc": r"\bN\s?C\b|CB (effective )?density|conduction band.*density", "Nv": r"\bN\s?V\b|VB (effective )?density|valence band.*density",
         "mun": r"electron mobility|μ\s?n|mu\s?n", "mup": r"hole mobility|μ\s?p|mu\s?p", "dop": r"donor|acceptor|N\s?[DA]\b|doping"}
failed = []


def get(u, raw=False):
    for wait in (5, 10, 20, 40, 80):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90).read()
            return b if raw else json.loads(b)
        except Exception as e:
            print("  retry", type(e).__name__, str(e)[:70], flush=True)
            if "400" in str(e) or "404" in str(e):
                return None
            time.sleep(wait)
    return None


def cells(tr):
    return [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


cands = []
for page_mark in ("*",):
    r = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
        {"query": QUERY, "format": "json", "pageSize": 100, "resultType": "lite", "sort": "P_PDATE_D desc",
         "cursorMark": page_mark}))
    if r is None:
        failed.append("search"); break
    print("hits", r.get("hitCount"), flush=True)
    cands += [(y["pmcid"], y.get("doi"), y.get("pubYear"), y.get("title", "")[:120])
              for y in r["resultList"]["result"] if y.get("pmcid")]
scored = []
for pmc, doi, yr, title in cands:
    fp = os.path.join(OUT, f"{pmc}.xml")
    if not os.path.exists(fp):
        b = get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML", raw=True)
        if not b:
            failed.append(pmc); continue
        open(fp, "wb").write(b)
    x = open(fp, encoding="utf-8", errors="replace").read()
    lic = (re.findall(r"creativecommons.org/licenses/[a-z\-]+/[\d.]+", x) or [None])[0]
    best = None
    for ti, tw in enumerate(re.findall(r"<table-wrap.*?</table-wrap>", x, re.S)):
        rows = [cells(tr) for tr in re.findall(r"<tr.*?</tr>", tw, re.S)]
        rows = [r_ for r_ in rows if r_]
        if len(rows) < 6:
            continue
        head = " || ".join(" | ".join(r_) for r_ in rows[:2])
        mats = [m for m, p in MATS.items() if re.search(p, head, re.I)]
        props = [k for k, p in PROPS.items() if any(re.search(p, r_[0], re.I) for r_ in rows if r_)]
        if len(props) >= 7 and mats and (best is None or len(mats) > len(best["materials"])):
            best = {"table_index": ti, "materials": mats, "props": props, "header": head[:300]}
    if best:
        scored.append({"pmcid": pmc, "doi": doi, "year": yr, "title": title, "licence": lic, **best})
scored.sort(key=lambda s: (-len(s["materials"]), -int(s["year"] or 0)))
json.dump({"query": QUERY, "n_candidates": len(cands), "failed": failed, "ranked": scored},
          open(os.path.join(OUT, "g1s2_sources.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for s in scored[:15]:
    print(len(s["materials"]), s["materials"], s["pmcid"], s["year"], (s["licence"] or "none").split("licenses/")[-1],
          "|", s["title"][:80])
print("candidates", len(cands), "with a qualifying table", len(scored))
if failed:
    raise SystemExit(f"INCOMPLETE: {failed}")
