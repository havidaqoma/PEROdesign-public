"""Build perodesign/library/g1s2r2_overlay.yaml (G1 step 2 ROUND 2, amendment C1) from the round-1 overlay by replacing
the Spiro-OMeTAD and TiO2-c values with the chosen C1-qualifying source table (data/sources/g1s2r2/*.txt, every number
read from the saved table) and REMOVING PEDOT:PSS and PCBM-60 (no C1-qualifying source; stacks with them become
'invalid' = not simulable in round 2, counted). Same conversion rules as round 1 (build_g1s2_overlay.py):
E_c = chi; E_v = chi + Eg; N_c = sqrt(Nc*Nv); cm->m; no bulk traps in TLs; other keys unchanged from round 1.
Usage: python scripts/build_g1s2r2_overlay.py [--spiro <source id>] [--tio2 <source id>]
Defaults = first candidate in rank order (phase0/g1s2/round2/qualification.json). "none" = material not simulable
(all its qualifying tables failed the C1 convergence pre-check)."""
import argparse
import copy
import json
import math
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "sources" / "g1s2r2"
Q = json.loads((REPO / "phase0" / "g1s2" / "round2" / "qualification.json").read_text(encoding="utf-8"))
RANK = Q["candidates_per_material_in_rank_order"]
ROWS = {"Eg": r"^(Band ?gap|E g\b)", "chi": r"^(Electron affinity|Χ)", "eps": r"^(Dielectric permittivity|ε r)",
        "Nc": r"^(CB effective density|N c\b)", "Nv": r"^(VB effective density|N v\b)", "mun": r"^(Electron mobility|µ n)",
        "mup": r"^(Hole mobility|µ p)", "ND": r"^(Shallow donor|N D\b)", "NA": r"^(Shallow acceptor|N A\b)"}
COLS = {"Spiro": r"^spiro", "TiO2": r"^TiO 2"}


def sci(cell):
    """'10 19'->1e19 ; '5·10 16'->5e16 ; '10 −4'->1e-4 ; '1.2 × 10 19'->1.2e19 ; '2.7 [ 2 ]'->2.7 ; '0'->0"""
    c = re.sub(r"\[[^\]]*\]", "", cell).replace("−", "-").strip()
    m = re.fullmatch(r"(?:(-?[\d.]+)\s*[·×]\s*)?10\s+(-?\d+)", c)
    if m:
        return float(m.group(1) or 1) * 10 ** int(m.group(2))
    return float(c.replace(",", "."))


def column(sid, mat):
    lines = [ln for ln in (SRC / f"{sid}.txt").read_text(encoding="utf-8").split("## TABLES", 1)[1]
             .split("## C1.2", 1)[0].splitlines() if ln.strip() and not ln.startswith("#")]
    head = [h.strip() for h in lines[0].split(" | ")]
    idx = [i for i, h in enumerate(head) if re.search(COLS[mat], h, re.I)]
    if len(idx) != 1:
        raise SystemExit(f"{sid}: column {mat} matched {idx} in {head}")
    vals, cells = {}, {}
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(head):
            raise SystemExit(f"{sid}: row width {len(parts)} != header {len(head)}: {ln[:80]}")
        for k, rx in ROWS.items():
            if k not in vals and re.search(rx, parts[0], re.I):
                vals[k], cells[parts[0]] = sci(parts[idx[0]]), parts[idx[0]]
    miss = set(ROWS) - set(vals)
    if miss:
        raise SystemExit(f"{sid}: rows missing for {mat}: {miss}")
    return vals, cells, head[idx[0]]


ap = argparse.ArgumentParser()
ap.add_argument("--spiro", default=RANK["Spiro"][0] if RANK["Spiro"] else None)
ap.add_argument("--tio2", default=RANK["TiO2"][0] if RANK["TiO2"] else None)
a = ap.parse_args()
a.spiro = None if a.spiro == "none" else a.spiro
a.tio2 = None if a.tio2 == "none" else a.tio2
ov = yaml.safe_load((REPO / "perodesign" / "library" / "g1s2_overlay.yaml").read_text(encoding="utf-8"))
ov = copy.deepcopy(ov)
doi = {c["source_id"]: c["doi"] for c in Q["candidates"] if c.get("source_id")}
for name, key, sid in (("Spiro-OMeTAD", "Spiro", a.spiro), ("TiO2-c", "TiO2", a.tio2)):
    if sid is None:
        ov["materials"].pop(name)
        continue
    v, cells, colname = column(sid, key)
    m = ov["materials"][name]
    m["params"].update({"eps_r": v["eps"], "E_c_eV": round(v["chi"], 4), "E_v_eV": round(v["chi"] + v["Eg"], 4),
                        "N_c_m3": float(f"{math.sqrt(v['Nc'] * v['Nv']) * 1e6:.6e}"),
                        "N_D_m3": float(f"{v['ND'] * 1e6:.6e}"), "N_A_m3": float(f"{v['NA'] * 1e6:.6e}"),
                        "mu_n_m2_Vs": float(f"{v['mun'] * 1e-4:.6e}"), "mu_p_m2_Vs": float(f"{v['mup'] * 1e-4:.6e}"),
                        "N_t_bulk_m3": 0})
    m["provenance"] = {"status": "literature", "file": f"g1s2r2/{sid}.txt"}
    m["literature"] = {"source": sid, "doi": doi[sid], "column": colname, "cells": cells,
                       "mapping": "E_c = chi; E_v = chi + Eg; N_c = sqrt(Nc*Nv); cm->m; no bulk traps in TLs; other keys "
                                  "as round 1. Label: from a device-fitted simulation paper (amendment C1)."}
for name in ("PEDOT:PSS", "PCBM-60"):          # no C1-qualifying source
    ov["materials"].pop(name, None)
ov["interfaces"] = {k: v for k, v in ov["interfaces"].items() if all(p in ov["materials"] or p in
                    ("MAPbI3", "C60", "SnO2", "PTAA", "NiOx") for p in k.split("|"))}
ov["README"] = ("G1 step 2 ROUND 2 overlay (amendment C1). Loaded on top of materials_v2.yaml by scripts/g1s2_run.py when "
                f"G1S2_ROUND=2. Built by scripts/build_g1s2r2_overlay.py --spiro {a.spiro} --tio2 {a.tio2}. "
                "PEDOT:PSS and PCBM-60 removed (no C1-qualifying source).")
ov["round2_choice"] = {"Spiro-OMeTAD": a.spiro, "TiO2-c": a.tio2}
(REPO / "perodesign" / "library" / "g1s2r2_overlay.yaml").write_text(
    "# GENERATED by scripts/build_g1s2r2_overlay.py - do not edit by hand\n" + yaml.safe_dump(ov, sort_keys=False, allow_unicode=True),
    encoding="utf-8")
for k in ("Spiro-OMeTAD", "TiO2-c"):
    if k in ov["materials"]:
        p = ov["materials"][k]["params"]
        print(f"{k:13s} src {ov['round2_choice'][k]} Ec {p['E_c_eV']} Ev {p['E_v_eV']} Nc {p['N_c_m3']:.3e} ND {p['N_D_m3']:.2e} "
              f"NA {p['N_A_m3']:.2e} mun {p['mu_n_m2_Vs']:.2e} mup {p['mu_p_m2_Vs']:.2e} eps {p['eps_r']}")
print("materials", sorted(ov["materials"]), "interfaces", len(ov["interfaces"]))
