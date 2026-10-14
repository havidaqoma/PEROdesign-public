"""G1 step 2 round-2 material-source search (docs/G1_step2_preregistration.md amendment C1).
Fixed Europe PMC queries -> open-access full texts -> tables giving the 8 properties (eps, Eg, chi, Nc, Nv, mu_n, mu_p,
doping) for any of Spiro-OMeTAD, TiO2, PEDOT:PSS, PCBM, BCP. For each candidate it also records DEVICE-FIT EVIDENCE
sentences (fabrication + drift-diffusion simulation compared with own measurement) for a HUMAN reading; the script
never decides rule C1.2 by itself. Ranking = number of the 4 C1 materials (+BCP) covered, then newer paper.
Any failed request (after retries) -> non-zero exit, never "no results".
Usage: python scripts/find_g1s2r2_sources.py <cache dir> -> <cache dir>/g1s2r2_sources.json"""
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
OA = ' AND OPEN_ACCESS:y AND (LICENSE:"cc by" OR LICENSE:"cc-by" OR LICENSE:"cc by-nc" OR LICENSE:"cc by-nc-nd" OR LICENSE:"cc by-nc-sa")'
SIMS = '(SCAPS OR SIMsalabim OR SETFOS OR Driftfusion OR IonMonger OR gpvdm OR COMSOL OR "drift-diffusion" OR "drift diffusion")'
DEVICE = '("fabricated" OR "experimental" OR "measured") AND ("J-V" OR "current density-voltage" OR "J–V")'
QUERIES = [
    f'perovskite AND {SIMS} AND {DEVICE} AND ("Spiro-OMeTAD" OR "spiro-MeOTAD") AND "electron affinity"' + OA,
    f'perovskite AND {SIMS} AND {DEVICE} AND "PEDOT:PSS" AND "electron affinity"' + OA,
    f'perovskite AND {SIMS} AND {DEVICE} AND (PCBM OR PC61BM OR "PC 61 BM") AND "electron affinity"' + OA,
    f'perovskite AND {SIMS} AND {DEVICE} AND TiO2 AND ("compact" OR "c-TiO2" OR "blocking layer") AND "electron affinity"' + OA,
]
MATS = {"Spiro": r"spiro", "TiO2": r"\bTiO\s?2\b|c-TiO", "PEDOT": r"PEDOT", "PCBM": r"PC\s?\[?6?1?\]?\s?BM|PCBM", "BCP": r"\bBCP\b"}
PROPS = {"eps": r"permittiv|dielectric|ε", "Eg": r"band\s?gap|E\s?g\b", "chi": r"electron affinity|χ",
         "Nc": r"\bN\s?C\b|CB (effective )?density|conduction band.*density", "Nv": r"\bN\s?V\b|VB (effective )?density|valence band.*density",
         "mun": r"electron mobility|μ\s?n|mu\s?n|µ\s?n", "mup": r"hole mobility|μ\s?p|mu\s?p|µ\s?p", "dop": r"donor|acceptor|N\s?[DA]\b|doping"}
EVID = re.compile(r"[^.]*\b(fabricat\w*|experimental(ly)?|measured)\b[^.]*\b(simulat\w*|SCAPS|drift[- ]diffusion|fit\w*|model\w*)\b[^.]*\.|"
                  r"[^.]*\b(simulat\w*|SCAPS|drift[- ]diffusion)\b[^.]*\b(experimental|measured|fabricated)\b[^.]*\.", re.I)
failed = []


def get(u, raw=False):
    for wait in (5, 10, 20, 40, 80, 120):
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


def text_of(x):
    body = re.sub(r"<table-wrap.*?</table-wrap>|<ref-list.*?</ref-list>", " ", x, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())


cands = {}
for qi, q in enumerate(QUERIES):
    cursor, n = "*", 0
    while cursor and n < 300:
        r = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
            {"query": q, "format": "json", "pageSize": 100, "resultType": "lite", "sort": "P_PDATE_D desc",
             "cursorMark": cursor}))
        if r is None:
            failed.append(f"search q{qi}"); break
        res = r["resultList"]["result"]
        if qi == 0 or cursor == "*":
            print(f"q{qi} hits", r.get("hitCount"), flush=True)
        for y in res:
            if y.get("pmcid"):
                cands.setdefault(y["pmcid"], (y.get("doi"), y.get("pubYear"), y.get("title", "")[:140], set()))[3].add(qi)
        n += len(res)
        nxt = r.get("nextCursorMark")
        cursor = nxt if (res and nxt != cursor) else None
print("unique candidates", len(cands), flush=True)
scored, missing = [], []
for pmc, (doi, yr, title, qs) in cands.items():
    fp = os.path.join(OUT, f"{pmc}.xml")
    if not os.path.exists(fp):
        b = get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML", raw=True)
        if not b:
            missing.append(pmc); continue
        open(fp, "wb").write(b)
    x = open(fp, encoding="utf-8", errors="replace").read()
    lic = (re.findall(r"creativecommons.org/licenses/[a-z\-]+/[\d.]+", x) or [None])[0]
    tabs = []
    for ti, tw in enumerate(re.findall(r"<table-wrap.*?</table-wrap>", x, re.S)):
        rows = [r_ for r_ in (cells(tr) for tr in re.findall(r"<tr.*?</tr>", tw, re.S)) if r_]
        if len(rows) < 6:
            continue
        head = " || ".join(" | ".join(r_) for r_ in rows[:2])
        mats = [m for m, p in MATS.items() if re.search(p, head, re.I)]
        props = [k for k, p in PROPS.items() if any(re.search(p, r_[0], re.I) for r_ in rows if r_)]
        if len(props) >= 7 and mats:
            tabs.append({"table_index": ti, "materials": mats, "props": props, "header": head[:300]})
    if not tabs:
        continue
    t = text_of(x)
    ev = [m.group(0).strip()[:400] for m in EVID.finditer(t)][:8]
    best = max(tabs, key=lambda s: len([m for m in s["materials"] if m != "BCP"]))
    scored.append({"pmcid": pmc, "doi": doi, "year": yr, "title": title, "licence": lic, "queries": sorted(qs),
                   "tables": tabs, "n_c1_materials": len({m for tb in tabs for m in tb["materials"] if m != "BCP"}),
                   "device_fit_evidence_candidates": ev})
scored.sort(key=lambda s: (-s["n_c1_materials"], -int(s["year"] or 0)))
json.dump({"queries": QUERIES, "n_candidates": len(cands), "failed": failed, "missing_fulltext": missing, "ranked": scored},
          open(os.path.join(OUT, "g1s2r2_sources.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for s in scored[:40]:
    print(s["n_c1_materials"], sorted({m for tb in s["tables"] for m in tb["materials"]}), s["pmcid"], s["year"],
          (s["licence"] or "none").split("licenses/")[-1], "ev", len(s["device_fit_evidence_candidates"]), "|", s["title"][:70])
print("candidates", len(cands), "with a qualifying table", len(scored), "missing full text", len(missing))
if failed or missing:
    raise SystemExit(f"INCOMPLETE: failed {failed} missing {missing}")
