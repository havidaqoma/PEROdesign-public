"""Build perodesign/library/g1s2_overlay.yaml (G1 step 2, docs/G1_step2_preregistration.md §2 + amendment B1) from the
saved source tables, so every number is read from data/sources/g1s2/*.txt, not typed by hand.
Mapping (same rule as the production NiOx/SnO2 entries): E_c = chi; E_v = chi + Eg; N_c(SimSS) = sqrt(Nc*Nv);
cm^-3 -> m^-3 (x1e6); cm2/Vs -> m2/Vs (x1e-4). No bulk traps in transport layers (as production PTAA/C60).
Switches / ions / optics-model keys copied from production PTAA (hole side) or C60 (electron side):
simss_default_transferred. Also writes data/nk/nk_Spiro_const_n1p7.txt (n = 1.7, k = 0, flagged approximation).
Usage: python scripts/build_g1s2_overlay.py"""
import math
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "sources" / "g1s2"
PROD = yaml.safe_load((REPO / "perodesign" / "library" / "materials_v2.yaml").read_text(encoding="utf-8"))
ROWS = {"Eg": r"^Band ?gap", "chi": r"^Electron affinity", "eps": r"^Dielectric permittivity|^Dielectric Permittivity",
        "Nc": r"^CB (effective density|EDOS)", "Nv": r"^VB (effective density|EDOS)", "mun": r"^Electron mobility",
        "mup": r"^Hole mobility", "ND": r"^(Density of n-type|Shallow donor)", "NA": r"^(Density of p-type|Shallow Acceptor)"}


def sci(cell):
    """'2.8 × 10 19' -> 2.8e19 ; '0.0 × 10 0' -> 0 ; '2 × 10 −4' -> 2e-4 ; '3.0' -> 3.0 ; '0' -> 0"""
    c = cell.replace("−", "-").strip()
    m = re.fullmatch(r"(-?[\d.]+)\s*×\s*10\s*(-?\d+)", c)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    return float(c)


def table(src, header_regex):
    t = (SRC / src).read_text(encoding="utf-8").split("## TEXT")[0].split("## TABLES", 1)[1]
    for block in t.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if lines and re.search(header_regex, block):
            return lines
    raise SystemExit(f"table not found in {src}: {header_regex}")


def column(lines, col_regex, header_line=0):
    head = [h.strip() for h in lines[header_line].split(" | ")]
    width = max(len(ln.split(" | ")) for ln in lines[header_line + 1:])
    if len(head) == width - 1:          # sub-header row without the row-label cell: align it to the data rows
        head = [""] + head
    if len(head) != width:
        raise SystemExit(f"header has {len(head)} cells, data rows {width}: cannot align {head}")
    idx = [i for i, h in enumerate(head) if re.search(col_regex, h)]
    if len(idx) != 1:
        raise SystemExit(f"column {col_regex!r} matched {idx} in {head}")
    out, cells = {}, {}
    for ln in lines:
        parts = [p.strip() for p in ln.split(" | ")]
        for k, rx in ROWS.items():
            if re.search(rx, parts[0], re.I) and k not in out:
                out[k] = sci(parts[idx[0]])
                cells[parts[0]] = parts[idx[0]]
    missing = set(ROWS) - set(out)
    if missing:
        raise SystemExit(f"rows missing for {col_regex}: {missing}")
    return out, cells, head[idx[0]]


def material(vals, cells, colname, src, doi, template, roles, nk, tmin, tmax, note=""):
    p = {k: v for k, v in PROD["materials"][template]["params"].items()}      # switches, ions, optics model keys
    p.update({"eps_r": vals["eps"], "E_c_eV": round(vals["chi"], 4), "E_v_eV": round(vals["chi"] + vals["Eg"], 4),
              "N_c_m3": float(f"{math.sqrt(vals['Nc'] * vals['Nv']) * 1e6:.6e}"),
              "N_D_m3": float(f"{vals['ND'] * 1e6:.6e}"), "N_A_m3": float(f"{vals['NA'] * 1e6:.6e}"),
              "mu_n_m2_Vs": float(f"{vals['mun'] * 1e-4:.6e}"), "mu_p_m2_Vs": float(f"{vals['mup'] * 1e-4:.6e}"),
              "N_t_bulk_m3": 0, "nk_file": nk})
    return {"roles": roles, "provenance": {"status": "literature", "file": f"g1s2/{src}"},
            "literature": {"source": src.replace(".txt", ""), "doi": doi, "column": colname, "cells": cells,
                           "mapping": "E_c = chi; E_v = chi + Eg; N_c = sqrt(Nc*Nv); cm->m; no bulk traps in TLs; "
                                      f"switches/ions from production {template} (simss_default_transferred). {note}"},
            "thickness_nm": {"min": tmin, "max": tmax, "provenance": "g1s2_database_range"},
            "params": p, "overridable": {}}


nj = table("njema2025_rscadv.txt", r"Spiro-OMeTAD 4,19 \| N719")
po = table("pochont2022_molecules.txt", r"PEDOT: PSS \[ 58 \]")
spiro, spc, spn = column(nj, r"^Spiro")
pcbm, pcc, pcn = column(nj, r"^PC61BM")
tio2, tic, tin = column(nj, r"^TiO 2")
pedot, pec, pen = column(po, r"^PEDOT", header_line=1)
NJ_DOI, PO_DOI = "10.1039/d5ra06604b", "10.3390/molecules27227927"
mats = {
    "Spiro-OMeTAD": material(spiro, spc, spn, "njema2025_rscadv.txt", NJ_DOI, "PTAA", ["HTL"], "nk_Spiro_const_n1p7.txt",
                             20, 1000, "nk: constant n = 1.7, k = 0 (no SimSS file; flagged approximation)."),
    "PCBM-60": material(pcbm, pcc, pcn, "njema2025_rscadv.txt", NJ_DOI, "C60", ["ETL", "buffer"], "nk_PCBM.txt", 5, 300),
    "TiO2-c": material(tio2, tic, tin, "njema2025_rscadv.txt", NJ_DOI, "C60", ["ETL", "buffer"], "nk_TiO2.txt", 5, 300,
                       "Source lists N_A 9e16 / N_D 0 for this ETL (likely row swap, amendment B1); used VERBATIM; "
                       "sensitivity S1 flips it."),
    "PEDOT:PSS": material(pedot, pec, pen, "pochont2022_molecules.txt", PO_DOI, "PTAA", ["HTL"], "nk_PEDOT.txt", 5, 300),
}
itf_e = PROD["interfaces"]["MAPbI3|C60"]["params"]
itf_h = PROD["interfaces"]["MAPbI3|PTAA"]["params"]
itf_none = PROD["interfaces"]["C60|SnO2"]["params"]
tl = lambda p, what: {"provenance": {"status": "simss_default_transferred", "from": what}, "params": dict(p),
                      "overridable": {}}
interfaces = {}
for etl in ("TiO2-c", "PCBM-60", "C60", "SnO2"):
    interfaces[f"{etl}|MAPbI3"] = tl(itf_e, "C60|MAPbI3 == MAPbI3|C60 electron-side values")   # n-i-p
    interfaces[f"MAPbI3|{etl}"] = tl(itf_e, "MAPbI3|C60 (electron side)")                      # p-i-n
for htl in ("Spiro-OMeTAD", "PTAA", "PEDOT:PSS", "NiOx"):
    interfaces[f"MAPbI3|{htl}"] = tl(itf_h, "MAPbI3|PTAA (hole side)")                         # n-i-p
    interfaces[f"{htl}|MAPbI3"] = tl(itf_h, "MAPbI3|PTAA (hole side)")                         # p-i-n
interfaces["TiO2-c|PCBM-60"] = tl(itf_none, "C60|SnO2 (TL/TL, no traps)")
interfaces["PCBM-60|C60"] = tl(itf_none, "C60|SnO2 (TL/TL, no traps)")
overlay = {
    "README": "G1 step 2 overlay. Loaded ON TOP of materials_v2.yaml by scripts/g1s2_run.py only; the production "
              "library is unchanged. Built by scripts/build_g1s2_overlay.py from data/sources/g1s2/. "
              "Pre-registration: docs/G1_step2_preregistration.md (incl. amendment B1).",
    "materials": mats,
    "material_patches": {"MAPbI3": {"thickness_nm": {"min": 50, "max": 2000, "provenance": "g1s2 §2"}},
                         "SnO2": {"roles": ["buffer", "ETL"],
                                  "thickness_nm": {"min": 5, "max": 300, "provenance": "g1s2 validation guard"}},
                         "C60": {"roles": ["ETL", "buffer"],
                                 "thickness_nm": {"min": 5, "max": 300, "provenance": "g1s2 validation guard"}},
                         "PTAA": {"thickness_nm": {"min": 5, "max": 300, "provenance": "g1s2 validation guard"}},
                         "NiOx": {"thickness_nm": {"min": 5, "max": 300, "provenance": "g1s2 validation guard"}}},
    "interfaces": interfaces,
    "architectures": {"n-i-p": ["ETL", "absorber", "HTL"], "n-i-p2": ["buffer", "ETL", "absorber", "HTL"],
                      "p-i-n": ["HTL", "absorber", "ETL"], "p-i-n2": ["HTL", "absorber", "ETL", "buffer"]},
    "architecture_setup": {"n-i-p": {"W_L_eV": "sfb", "W_R_eV": "sfb"}, "n-i-p2": {"W_L_eV": "sfb", "W_R_eV": "sfb"},
                           "p-i-n": dict(PROD["architecture_setup"]["p-i-n"]),
                           "p-i-n2": dict(PROD["architecture_setup"]["p-i-n"])},
}
(REPO / "perodesign" / "library" / "g1s2_overlay.yaml").write_text(
    "# GENERATED by scripts/build_g1s2_overlay.py - do not edit by hand\n" + yaml.safe_dump(overlay, sort_keys=False,
                                                                                          allow_unicode=True),
    encoding="utf-8")
nk = REPO / "data" / "nk" / "nk_Spiro_const_n1p7.txt"
nk.write_text("lambda n k\n" + "".join(f"{(300 + 5 * i) * 1e-9:.4e} 1.7 0\n" for i in range(181)), encoding="utf-8")
# NiOx/SnO2 constant files in data/nk/ use the same 300-1200 nm, 5 nm grid (182 lines incl. header)
for k, m in mats.items():
    p = m["params"]
    print(f"{k:13s} Ec {p['E_c_eV']} Ev {p['E_v_eV']} Nc {p['N_c_m3']:.3e} ND {p['N_D_m3']:.2e} NA {p['N_A_m3']:.2e} "
          f"mun {p['mu_n_m2_Vs']:.2e} mup {p['mu_p_m2_Vs']:.2e} eps {p['eps_r']}")
