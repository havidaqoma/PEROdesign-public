"""Paper B pilot, run BEFORE the pre-registration is frozen and disclosed in it (§9). Output phase0/paperB/pilot.json.

Purpose (go/no-go for the design, not a result):
  P1 convergence: every (stack, HTL, metal) combination runs at the Paper A reference thicknesses and at the two box
     corners (all min / all max), base scenario, plus the reference design in the worse / better scenarios.
  P2 degeneracy check (skill lesson from Paper A): 8 Sobol points per combination (seed 1000, NOT a run seed), to see
     whether module PCE and USD/W are still almost perfectly anti-correlated once materials vary.
Usage (WSL): ~/venvs/perodesign-dev/bin/python scripts/paperB_pilot.py [workers]
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "phase0" / "paperB"
CACHE = Path(os.environ.get("PAPERB_CACHE", Path.home() / "perodesign_p1" / "paperB_simss_cache"))
PILOT_SEED = 1000


def jobs():
    from perodesign.optim import objective as A
    from perodesign.optim import objective_b as B
    from perodesign.optim import search as SA
    out = []
    for arch in B.STACKS:
        sp = B.space(arch)
        for hi, htl in enumerate(B.HTLS):
            lo_b, hi_b = B.bounds(arch, htl)
            ref = [min(max(v, a), b) for v, a, b in zip(A.REFERENCE[arch], lo_b, hi_b)]
            ref_u = [(v - a) / (b - a) for v, a, b in zip(ref, lo_b, hi_b)]
            for mi, metal in enumerate(B.METALS):
                cats = [hi, mi]
                out.append((arch, "reference", ref_u, cats, "base"))
                out.append((arch, "reference", ref_u, cats, "worse"))
                out.append((arch, "reference", ref_u, cats, "better"))
                out.append((arch, "corner_min", [0.0] * sp.n_cont, cats, "base"))
                out.append((arch, "corner_max", [1.0] * sp.n_cont, cats, "base"))
                for k, u in enumerate(SA.sobol_points(sp.n_cont, 8, PILOT_SEED)):
                    out.append((arch, f"sobol{k}", [float(v) for v in u], cats, "base"))
    return out


def _one(job):
    from perodesign.optim import objective_b as B
    arch, what, u, cats, scen = job
    r = B.evaluate(arch, u, cats, scen, cache_dir=CACHE)
    r["what"] = what
    return r


def main(workers):
    from scipy.stats import spearmanr
    from perodesign.optim import objective_b as B
    OUT.mkdir(parents=True, exist_ok=True)
    J = jobs()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        R = list(ex.map(_one, J))
    res = {"schema": "perodesign.paperB_pilot/1", "pilot_seed": PILOT_SEED, "n_sims": len(R),
           "ref_point": {a: B.reference_point(a) for a in B.STACKS}, "records": R, "summary": {}}
    for arch in B.STACKS:
        rs = [r for r in R if r["arch"] == arch]
        conv = {f"{h}/{m}": [r["what"] + ":" + r["scenario"] for r in rs if r["HTL"] == h and r["metal"] == m
                             and not r["feasible"]] for h in B.HTLS for m in B.METALS}
        base = [r for r in rs if r["feasible"] and r["scenario"] == "base"]
        rho = spearmanr([r["module_pce_pct"] for r in base], [r["usd_per_W"] for r in base]).statistic
        by_combo = {}
        for h in B.HTLS:
            for m in B.METALS:
                c = [r for r in base if r["HTL"] == h and r["metal"] == m]
                if c:
                    by_combo[f"{h}/{m}"] = {"n": len(c), "pce_max": max(r["module_pce_pct"] for r in c),
                                            "usd_min": min(r["usd_per_W"] for r in c),
                                            "usd_max": max(r["usd_per_W"] for r in c)}
        from perodesign.optim.search import pareto
        pf = pareto([(r["module_pce_pct"], r["usd_per_W"]) for r in base])
        combos_on_front = sorted({f"{r['HTL']}/{r['metal']}" for r in base
                                  if (r["module_pce_pct"], r["usd_per_W"]) in set(pf)})
        res["summary"][arch] = {"infeasible_by_combo": conv, "n_feasible_base": len(base),
                                "spearman_pce_usd": rho, "by_combo": by_combo,
                                "pilot_front": pf, "combos_on_pilot_front": combos_on_front}
        print(arch, "infeasible:", {k: v for k, v in conv.items() if v}, "rho", round(rho, 3), flush=True)
        for k, v in by_combo.items():
            print("  ", k, v, flush=True)
        print("   front", [(round(p, 2), round(c, 3)) for p, c in pf], combos_on_front, flush=True)
    (OUT / "pilot.json").write_text(json.dumps(res, indent=1))
    print("ref_point", res["ref_point"])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
