"""Verify the 90 Paper B run files before analysis (deterministic checks; prints a summary, exits non-zero on failure).
Run in WSL: python scripts/paperB_verify_runs.py <runs_dir>"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import objective_b as B  # noqa: E402

d = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "phase0" / "paperB" / "runs"
files = sorted(d.glob("*.json"))
bad = []
ov = B.overlay_sha256()
n_calls = n_inf = 0
dup_runs = Counter()
for f in files:
    r = json.loads(f.read_text())
    a, s, m, k = f.stem.split("__")
    if r["run_id"] != f.stem:
        bad.append(f"{f.name}: run_id {r['run_id']}")
    if len(r["calls"]) != 240:
        bad.append(f"{f.name}: {len(r['calls'])} calls")
    if [c["call"] for c in r["calls"]] != list(range(240)):
        bad.append(f"{f.name}: call indices")
    if r["overlay_sha256"] != ov:
        bad.append(f"{f.name}: overlay sha {r['overlay_sha256'][:12]} != {ov[:12]}")
    if r["n_infeasible"] != sum(not c["feasible"] for c in r["calls"]):
        bad.append(f"{f.name}: n_infeasible mismatch")
    for c in r["calls"]:
        lib = B.physics_library(a, c["HTL"], c["metal"])
        if c["library_sha256"] != lib["_sha256"]:
            bad.append(f"{f.name}: call {c['call']} library sha")
            break
        if c["feasible"] and not (0 < c["module_pce_pct"] < 40 and c["usd_per_W"] > 0):
            bad.append(f"{f.name}: call {c['call']} values")
            break
    if r["n_infeasible"] > 12:
        print("UNRELIABLE-RULE run", f.stem, r["n_infeasible"])
    n_calls += len(r["calls"])
    n_inf += r["n_infeasible"]
first24 = {}
for f in files:
    a, s, m, k = f.stem.split("__")
    r = json.loads(f.read_text())
    first24.setdefault((a, s, k), {})[m] = [(c["u"], c["cats"]) for c in r["calls"][:24]]
for key, v in first24.items():
    if len({json.dumps(x) for x in v.values()}) != 1:
        bad.append(f"shared start differs for {key}")
print(f"files {len(files)} calls {n_calls} infeasible {n_inf} overlay {ov[:12]}")
print("PROBLEMS" if bad else "ALL CHECKS PASS", bad[:10])
sys.exit(1 if bad or len(files) != 90 else 0)
