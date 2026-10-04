"""Paper B figures and tables from phase0/paperB/result.json + runs/ (+ swf.json if present).
  python scripts/paperB_figures.py [out_dir]   -> phase0/paperB/figures/*.png + tables.md
Every number in tables.md is read from the result files; nothing is typed in by hand."""
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import search as S  # noqa: E402

B_DIR = REPO / "phase0" / "paperB"
ARCHS = ("p-i-n", "n-i-p")
SCENS = ("base", "worse", "better")
METHODS = ("random", "nsga2", "mixbo")
LABEL = {"random": "Sobol random", "nsga2": "mixed NSGA-II", "mixbo": "mixed BO (qLogNEHVI)"}
COLOR = {"random": "#999999", "nsga2": "#E69F00", "mixbo": "#0072B2"}
COMBOS = [f"{h}/{m}" for h in ("NiOx", "PTAA") for m in ("Cu", "Ag", "Au")]
# Okabe-Ito: metal = colour, HTL = marker
MCOL = {"Cu": "#D55E00", "Ag": "#0072B2", "Au": "#E69F00"}
HMARK = {"NiOx": "o", "PTAA": "^"}
STACK = {"p-i-n": r"p-i-n  HTL/MAPbI$_3$/C$_{60}$/SnO$_2$/ITO/metal", "n-i-p": r"n-i-p  C$_{60}$/MAPbI$_3$/HTL/metal"}


def load(runs_dir):
    runs = {}
    for p in sorted(Path(runs_dir).glob("*.json")):
        r = json.loads(p.read_text())
        a, s, m, k = p.stem.split("__")
        runs[(a, s, m, int(k[1:]))] = r
    return runs


def ys(run):
    return [{"y": ([c["module_pce_pct"], c["log10_usd_per_W"]] if c["feasible"] else None)} for c in run["calls"]]


def fig_fronts(res, runs, out):
    """Every feasible design (base scenario), coloured by metal, marker by HTL; pooled front drawn; per stack."""
    from matplotlib.lines import Line2D
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.8))
    for ax, a in zip(axs, ARCHS):
        cs = [c for (aa, ss, m, k), r in runs.items() if aa == a and ss == "base" for c in r["calls"] if c["feasible"]]
        for cb in COMBOS:
            h, mt = cb.split("/")
            sel = [c for c in cs if c["HTL"] == h and c["metal"] == mt]
            if sel:
                ax.scatter([c["module_pce_pct"] for c in sel], [c["usd_per_W"] for c in sel], s=5, marker=HMARK[h],
                           color=MCOL[mt], alpha=0.25, lw=0, rasterized=True)
        fr = res["cases"][f"{a}/base"]["q2"]["front"]
        ax.plot([p for p, _, _ in fr], [u for _, u, _ in fr], "-", color="k", lw=1.0, zorder=5)
        for p, u, cb in fr:
            h, mt = cb.split("/")
            ax.plot(p, u, HMARK[h], ms=9, mfc=MCOL[mt], mec="k", mew=1.0, zorder=6)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_xlabel("module PCE (%)")
        ax.set_ylabel("cost (USD/W, Malaysia, log scale)")
        ax.set_title(STACK[a], fontsize=10)
    handles = [Line2D([], [], ls="none", marker="s", ms=7, color=MCOL[m], label=m) for m in MCOL]
    handles += [Line2D([], [], ls="none", marker=HMARK[h], ms=7, color="0.4", label=h) for h in HMARK]
    handles += [Line2D([], [], color="k", marker="o", mfc="white", mec="k", label="pooled Pareto front")]
    fig.legend(handles=handles, loc="lower center", ncol=6, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "figB1_fronts.png", dpi=200)
    plt.close(fig)


def fig_front_zoom(res, runs, out):
    """Cheap corner (no Au): the part of the space where the front lives, all 3 scenarios."""
    fig, axs = plt.subplots(2, 3, figsize=(12.5, 7))
    for i, a in enumerate(ARCHS):
        for j, s in enumerate(SCENS):
            ax = axs[i, j]
            cs = [c for (aa, ss, m, k), r in runs.items() if aa == a and ss == s for c in r["calls"]
                  if c["feasible"] and c["metal"] != "Au"]
            for cb in COMBOS:
                h, mt = cb.split("/")
                sel = [c for c in cs if c["HTL"] == h and c["metal"] == mt]
                if sel:
                    ax.scatter([c["module_pce_pct"] for c in sel], [c["usd_per_W"] for c in sel], s=5,
                               marker=HMARK[h], color=MCOL[mt], alpha=0.3, lw=0, rasterized=True)
            fr = res["cases"][f"{a}/{s}"]["q2"]["front"]
            ax.plot([p for p, _, _ in fr], [u for _, u, _ in fr], "-", color="k", lw=1.0, zorder=5)
            for p, u, cb in fr:
                h, mt = cb.split("/")
                ax.plot(p, u, HMARK[h], ms=8, mfc=MCOL[mt], mec="k", mew=1.0, zorder=6)
            top = max(p for p, _, _ in fr)
            ax.set_xlim(top - 3.0, top + 0.3)
            lo_u = min(u for _, u, _ in fr)
            ax.set_ylim(lo_u * 0.95, lo_u * 2.0)
            ax.set_title(f"{a}, {s}", fontsize=10)
            if j == 0:
                ax.set_ylabel("USD/W")
            if i == 1:
                ax.set_xlabel("module PCE (%)")
    fig.tight_layout()
    fig.savefig(out / "figB2_front_zoom.png", dpi=200)
    plt.close(fig)


def fig_hv_igd(res, runs, out):
    fig, axs = plt.subplots(2, 3, figsize=(12, 6.5), sharex=True)
    for i, a in enumerate(ARCHS):
        for j, s in enumerate(SCENS):
            ax = axs[i, j]
            ref = res["cases"][f"{a}/{s}"]["ref_point"]
            for m in METHODS:
                C = np.array([S.hv_curve(ys(runs[(a, s, m, k)]), ref) for k in range(5)])
                mu, sd = C.mean(0), C.std(0, ddof=1)
                x = np.arange(1, C.shape[1] + 1)
                ax.plot(x, mu, color=COLOR[m], label=LABEL[m])
                ax.fill_between(x, mu - 2.776 * sd / np.sqrt(5), mu + 2.776 * sd / np.sqrt(5), color=COLOR[m], alpha=0.2)
            hi = res["cases"][f"{a}/{s}"]["best_hv_any_run"]
            ax.set_ylim(0.9 * hi, 1.005 * hi)
            ax.set_xlim(24, 242)
            ax.set_title(f"{a}, {s}", fontsize=10)
            if j == 0:
                ax.set_ylabel("hypervolume (%-pt x decades)")
            if i == 1:
                ax.set_xlabel("simulator calls")
    h, l = axs[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out / "figB3_hv_vs_calls.png", dpi=200)
    plt.close(fig)


def fig_call_share(res, out):
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.2), sharey=True)
    for ax, a in zip(axs, ARCHS):
        c = res["cases"][f"{a}/base"]
        x = np.arange(len(COMBOS))
        w = 0.27
        for k, m in enumerate(METHODS):
            sh = [100 * c["methods"][m]["call_share_by_combo"][cb] for cb in COMBOS]
            ax.bar(x + (k - 1) * w, sh, width=w, color=COLOR[m], label=LABEL[m])
        ax.set_xticks(x, COMBOS, rotation=30, fontsize=8)
        ax.set_title(f"{STACK[a]} (base)", fontsize=9)
        ax.set_ylabel("share of calls (%)")
        ax.axhline(100 / 6, color="k", lw=0.6, ls=":")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out / "figB4_call_share.png", dpi=200)
    plt.close(fig)


def f(v, spec):
    return "n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else format(v, spec)


def tables(res, runs, swf=None):
    L = ["# Paper B tables (generated by scripts/paperB_figures.py from phase0/paperB/result.json)", ""]
    L += ["## Q1a: final hypervolume after 240 calls (mean ± 95% CI, 5 seeds)", "",
          "| Case | " + " | ".join(LABEL[m] for m in METHODS) + " | Verdicts (CI non-overlap) | Calls to 95% (median) | Unreliable |",
          "|---|" + "---|" * (len(METHODS) + 3)]
    for k, c in res["cases"].items():
        ms = c["methods"]
        v = [kk for kk, b in c["q1"].items() if b] or ["no difference found"]
        L.append(f"| {k} | " + " | ".join(f"{ms[m]['hv_mean']:.4g} ± {ms[m]['hv_ci95_half']:.2g}" for m in METHODS)
                 + f" | {', '.join(v)} | " + ", ".join(f"{m} {ms[m]['calls_to_95pct_best_median']}" for m in METHODS)
                 + f" | {'YES' if c['unreliable'] else 'no'} |")
    L += ["", "## Q1b: IGD+ to the pooled front (mean ± 95% CI, lower is better); diagnostic no-Au HV", "",
          "| Case | " + " | ".join(f"{LABEL[m]} IGD+" for m in METHODS) + " | Verdicts | " +
          " | ".join(f"{LABEL[m]} HV no-Au" for m in METHODS) + " |", "|---|" + "---|" * (2 * len(METHODS) + 1)]
    for k, c in res["cases"].items():
        ms = c["methods"]
        v = [kk for kk, b in c["q1_igd"].items() if b] or ["no difference found"]
        L.append(f"| {k} | " + " | ".join(f"{ms[m]['igd_plus_mean']:.4f} ± {ms[m]['igd_plus_ci95_half']:.2g}" for m in METHODS)
                 + f" | {', '.join(v)} | " + " | ".join(f"{ms[m]['hv_no_au_mean']:.4g} ± {ms[m]['hv_no_au_ci95_half']:.2g}"
                                                         for m in METHODS) + " |")
    L += ["", "## Q2: pooled front, gap and wording (Malaysia line)", "",
          "| Case | Front (PCE %, USD/W, materials) | ΔPCE (pt) | ΔCost (%) | Small? | Wording | Spearman ρ |",
          "|---|---|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        q = c["q2"]
        fr = "; ".join(f"{p:.2f}, {u:.4f}, {cb}" for p, u, cb in q["front"])
        L.append(f"| {k} | {fr} | {q['gap_pce_points']:.3f} | {q['gap_cost_pct']:.2f} | {'yes' if q['gap_small'] else 'no'} | "
                 f"{q['wording']} | {q['spearman_pce_usd_pooled']:.3f} |")
    L += ["", "## Designs at the two ends of each front", "",
          "| Case | End | Materials | Design (nm, stripe mm) | Cell PCE % | Voc V | FF | Jsc mA/cm2 | Metal USD/m2 | USD/W (high prices) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        for which in ("pce_optimal", "cost_optimal"):
            d = c["q2"][which]
            L.append(f"| {k} | {which} | {d['combo']} | " + ", ".join(f"{n.replace('_nm', '').replace('_mm', '')} {v:g}"
                                                                   for n, v in d["x"].items())
                     + f" | {d['cell_pce_pct']:.2f} | {f(d['voc_V'], '.4f')} | {f(d['ff'], '.3f')} | {f(d['jsc_mA_cm2'], '.2f')} | "
                       f"{f(d['back_electrode_usd_m2'], '.3f')} | {d['usd_per_W']:.4f} ({d['usd_per_W_high_prices']:.4f}) |")
    L += ["", "## Best result per material combination (pooled)", "",
          "| Case | " + " | ".join(COMBOS) + " |", "|---|" + "---|" * len(COMBOS)]
    for k, c in res["cases"].items():
        pc = c["q2"]["per_combo"]
        L.append(f"| {k} | " + " | ".join(
            (f"{pc[cb]['best_pce']:.2f}% @ {pc[cb]['usd_per_W_at_best_pce']:.3f}; min {pc[cb]['min_usd_per_W']:.3f}"
             if cb in pc else "none") for cb in COMBOS) + " |")
    L += ["", "## CN / IN capital-rate row (same designs; only the capital rate changed)", "",
          "| Case | End | MY | CN | IN |", "|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        for which in ("pce_optimal", "cost_optimal"):
            r = c["q2"][which]["usd_per_W_by_rate_region"]
            L.append(f"| {k} | {which} | {r['MY']:.4f} | {r['CN']:.4f} | {r['IN']:.4f} |")
    L += ["", "## Q3: robustness over the 3 scenarios", "",
          "| Stack | Q1a robust | Q1b (IGD+) robust | PCE-opt materials | Cost-opt materials | Materials robust | Wording by scenario |",
          "|---|---|---|---|---|---|---|"]
    for a, q in res["q3"].items():
        m = q["optimal_combos_by_scenario"]
        L.append(f"| {a} | {q['q1_robust']} | {q['q1_igd_robust']} | {' / '.join(m['pce_optimal'])} | "
                 f"{' / '.join(m['cost_optimal'])} | {q['materials_robust']} | {' / '.join(q['wording_by_scenario'])} |")
    L += ["", "## Q4: break-even PTAA price (USD/g; current base price in the library)", "",
          "| Case | Metal | PTAA best (PCE %, USD/W) | NiOx best (PCE %, USD/W) | PTAA PCE advantage (pt) | Break-even vs NiOx | Break-even vs front cost-opt | Status |",
          "|---|---|---|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        q4 = c.get("q4") or {}
        for mt, v in (q4.get("by_metal") or {}).items():
            if v is None:
                L.append(f"| {k} | {mt} | none | none | n/a | n/a | n/a | missing combination |")
                continue
            L.append(f"| {k} | {mt} | {v['PTAA_best']['module_pce_pct']:.2f}, {v['PTAA_best']['usd_per_W']:.4f} | "
                     f"{v['NiOx_best']['module_pce_pct']:.2f}, {v['NiOx_best']['usd_per_W']:.4f} | "
                     f"{v['ptaa_pce_advantage_points']:.3f} | {f(v['break_even_vs_NiOx_usd_g'], '.1f')} | "
                     f"{f(v['break_even_vs_front_cost_optimal_usd_g'], '.1f')} | {v['status']} |")
    L += ["", "## Infeasible calls", "", "| Case | " + " | ".join(LABEL[m] for m in METHODS) + " | Reasons (all runs) |",
          "|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        a, s = k.split("/")
        reasons = {}
        for m in METHODS:
            for kk in range(5):
                for cc in runs[(a, s, m, kk)]["calls"]:
                    if not cc["feasible"]:
                        key = (cc.get("reason") or cc.get("sim_status") or "?")[:40]
                        reasons[key] = reasons.get(key, 0) + 1
        L.append(f"| {k} | " + " | ".join(str(sum(c["methods"][m]["n_infeasible"])) for m in METHODS)
                 + " | " + ("; ".join(f"{r} ×{n}" for r, n in sorted(reasons.items(), key=lambda t: -t[1])[:3]) or "none") + " |")
    if swf:
        L += ["", "## Sensitivity S-WF (n-i-p; anode = bare metal work function instead of B2)", "",
              "| Scenario | Materials | B2 (PCE %, USD/W) | metal WF (PCE %, USD/W) | status | Front with metal WF | Front under B2 |",
              "|---|---|---|---|---|---|---|"]
        for s, c in swf["cases"].items():
            fr = "; ".join(cb for _, _, cb in c["front_metal_wf"])
            for cb, v in c["rows"].items():
                mw = v["metal_wf"]
                L.append(f"| {s} | {cb} | {v['B2'][0]:.2f}, {v['B2'][1]:.4f} | "
                         f"{f(mw[0], '.2f')}, {f(mw[1], '.4f')} | {v['metal_wf_status']} | {fr} | {'; '.join(c['combos_on_B2_front'])} |")
    n_calls = sum(len(r["calls"]) for r in runs.values())
    n_sec = sum(c.get("seconds") or 0 for r in runs.values() for c in r["calls"])
    L += ["", f"Total calls {n_calls} across {len(runs)} runs; summed SimSS seconds {n_sec:.0f} (cache hits count 0 s)."]
    return "\n".join(L) + "\n"


def main(out=None, base=B_DIR):
    out = Path(out) if out else base / "figures"
    out.mkdir(parents=True, exist_ok=True)
    res = json.loads((base / "result.json").read_text())
    runs = load(base / "runs")
    if len(runs) != 90:
        raise SystemExit(f"expected 90 runs, found {len(runs)}")
    swf = json.loads((base / "swf.json").read_text()) if (base / "swf.json").exists() else None
    fig_fronts(res, runs, out)
    fig_front_zoom(res, runs, out)
    fig_hv_igd(res, runs, out)
    fig_call_share(res, out)
    (out / "tables.md").write_text(tables(res, runs, swf), encoding="utf-8")
    print("wrote", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
