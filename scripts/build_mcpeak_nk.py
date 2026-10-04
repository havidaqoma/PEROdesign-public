"""Convert refractiveindex.info McPeak 2015 metal files (CC0; data/nk/McPeak_<M>.yml) to SimSS nk tables
(data/nk/nk_<M>_McPeak2015.txt: header 'lambda n k', lambda in metres '%.4e', n and k as '%g' = 6 significant digits).

Gate: the Cu table produced this way must equal the committed data/nk/nk_Cu_McPeak2015.txt byte for byte
(it was made by hand in P1). Paper B uses the same conversion for Ag and Au.

Usage: python scripts/build_mcpeak_nk.py [--check-only]
"""
import sys
from pathlib import Path

import yaml

NK = Path(__file__).resolve().parents[1] / "data" / "nk"


def table(metal: str) -> str:
    y = yaml.safe_load((NK / f"McPeak_{metal}.yml").read_text(encoding="utf-8"))
    blocks = [d for d in y["DATA"] if d["type"] == "tabulated nk"]
    if len(blocks) != 1:
        raise SystemExit(f"{metal}: expected one 'tabulated nk' block, got {len(blocks)}")
    rows = ["lambda n k"]
    for line in blocks[0]["data"].strip().splitlines():
        um, n, k = line.split()
        rows.append(f"{float(um) * 1e-6:.4e} {float(n):g} {float(k):g}")
    return "\n".join(rows) + "\n"


def main(check_only: bool):
    ref = (NK / "nk_Cu_McPeak2015.txt").read_bytes()
    got = table("Cu").encode()
    if got != ref:
        a, b = ref.decode().splitlines(), got.decode().splitlines()
        diff = next((i for i, (x, z) in enumerate(zip(a, b)) if x != z), min(len(a), len(b)))
        raise SystemExit(f"GATE FAIL: converter does not reproduce nk_Cu_McPeak2015.txt (first diff at line {diff + 1}: "
                         f"{a[diff] if diff < len(a) else None!r} vs {b[diff] if diff < len(b) else None!r})")
    print("gate ok: Cu table reproduced byte for byte")
    if check_only:
        return
    for m in ("Ag", "Au"):
        out = NK / f"nk_{m}_McPeak2015.txt"
        out.write_bytes(table(m).encode())
        print("wrote", out.name, len(table(m).splitlines()) - 1, "rows")


if __name__ == "__main__":
    main("--check-only" in sys.argv)
