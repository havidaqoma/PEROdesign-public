"""Paper A figures and tables from phase0/paperA/result.json + runs/ (and P2 phase0/sensitivity/result.json).
  python scripts/paperA_figures.py [out_dir]   -> phase0/paperA/figures/*.png + tables.md
Every number in tables.md is read from the result files; nothing is typed in by hand."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import search as S  # noqa: E402

A = REPO / "phase0" / "paperA"
ARCHS = ("p-i-n", "n-i-p")
SCENS = ("base", "worse", "better")
METHODS = ("random", "nsga2", "qnehvi")
LABEL = {"random": "Sobol random", "nsga2": "NSGA-II", "qnehvi": "qNEHVI (BO)"}
# Okabe-Ito (colour-blind safe); scenarios also differ by line style in the fronts figure
COLOR = {"random": "#999999", "nsga2": "#E69F00", "qnehvi": "#0072B2", "base": "#000000", "worse": "#D55E00",
         "better": "#009E73"}
STACK = {"p-i-n": r"p-i-n NiO$_x$/MAPbI$_3$/C$_{60}$/SnO$_2$/Cu", "n-i-p": r"n-i-p C$_{60}$/MAPbI$_3$/PTAA/Au"}


def load(runs_dir):
    runs = {}
    for p in sorted(Path(runs_dir).glob("*.json")):
        r = json.loads(p.read_text())
        a, s, m, k = p.stem.split("__")
        runs[(a, s, m, int(k[1:]))] = r
    return runs


def ys(run):
    return [{"y": ([c["module_pce_pct"], c["usd_per_W"]] if c["feasible"] else None)} for c in run["calls"]]


def fig_hv(res, runs, out):
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
            lo = min(min(np.array([S.hv_curve(ys(runs[(a, s, m, k)]), ref) for k in range(5)]).mean(0)[S.N_INIT - 1]
                         for m in METHODS), min(res["cases"][f"{a}/{s}"]["methods"][m]["hv_mean"] for m in METHODS))
            hi = res["cases"][f"{a}/{s}"]["best_hv_any_run"]
            ax.set_ylim(lo - 0.05 * (hi - lo), hi + 0.05 * (hi - lo))
            ax.set_xlim(S.N_INIT, S.BUDGET + 2)            # curves start after the shared Sobol initial design
            ax.set_title(f"{a}, {s}", fontsize=10)
            if j == 0:
                ax.set_ylabel("hypervolume (%-pt x USD/W)")
            if i == 1:
                ax.set_xlabel("simulator calls")
    h, l = axs[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out / "fig2_hv_vs_calls.png", dpi=200)
    plt.close(fig)


def fig_fronts(res, runs, out):
    """Top row: cost per watt vs module PCE for every feasible design, optimum marked.
    Bottom row: materials cost per m2 vs module PCE (why the front collapses: M barely moves)."""
    from matplotlib.lines import Line2D
    fig, axs = plt.subplots(2, 2, figsize=(11, 8.4))
    for col, a in enumerate(ARCHS):
        top, bot = axs[0, col], axs[1, col]
        for s in SCENS:
            cs = [c for (aa, ss, m, k), r in runs.items() if aa == a and ss == s for c in r["calls"] if c["feasible"]]
            pce = np.array([c["module_pce_pct"] for c in cs])
            top.scatter(pce, [c["usd_per_W"] for c in cs], s=3, color=COLOR[s], alpha=0.18, lw=0, rasterized=True)
            bot.scatter(pce, [c["materials_usd_m2"] for c in cs], s=3, color=COLOR[s], alpha=0.18, lw=0, rasterized=True)
            d = res["cases"][f"{a}/{s}"]["q2"]["pce_optimal"]
            top.plot(d["module_pce_pct"], d["usd_per_W"], "*", ms=16, mfc=COLOR[s], mec="white", mew=1.0, zorder=6)
            bot.plot(d["module_pce_pct"], d["materials_usd_m2"], "*", ms=16, mfc=COLOR[s], mec="white", mew=1.0, zorder=6)
        top.set_yscale("log")
        top.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
        top.yaxis.set_minor_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}" if f"{v:.2g}"[0] in "25" else ""))
        top.set_ylabel("cost (USD/W, Malaysia, log scale)")
        bot.set_ylabel("materials cost (USD/m$^2$)")
        top.set_title(STACK[a], fontsize=10)
        for ax in (top, bot):
            ax.set_xlabel("module PCE (%)")
            lo_, hi_ = ax.get_xlim()
            ax.set_xlim(lo_, hi_ + 0.04 * (hi_ - lo_))
    handles = [Line2D([], [], ls="none", marker="o", ms=6, color=COLOR[s], label=f"{s} scenario (all feasible designs)")
               for s in SCENS]
    handles += [Line2D([], [], ls="none", marker="*", ms=13, mfc="0.3", mec="white", label="Pareto front (1 to 5 designs, overlapping)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out / "fig3_pareto_fronts.png", dpi=200)
    plt.close(fig)


def fig_cost_parts(res, out):
    """Share of each cost part at the front (PCE-optimal end), total printed above each bar."""
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.0))
    cols = {"materials": "#8C564B", "capital": "#CC79A7", "other_opex": "#56B4E9"}
    for ax, a in zip(axs, ARCHS):
        x = np.arange(len(SCENS))
        bottom = np.zeros(len(SCENS))
        tot = np.array([res["cases"][f"{a}/{s}"]["q2"]["pce_optimal"]["usd_per_W"] for s in SCENS])
        for k, col in cols.items():
            v = np.array([res["cases"][f"{a}/{s}"]["q2"]["pce_optimal"]["parts_usd_per_W"][k] for s in SCENS]) / tot * 100
            ax.bar(x, v, bottom=bottom, color=col, width=0.55, label=k.replace("_", " "))
            bottom += v
        for xi, t in zip(x, tot):
            ax.text(xi, 102, f"{t:.3g} USD/W", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x, [f"{s}" for s in SCENS])
        ax.set_ylim(0, 115)
        ax.set_ylabel("share of cost per watt (%)")
        ax.set_title(STACK[a], fontsize=10)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "fig4_cost_parts.png", dpi=200)
    plt.close(fig)


def fig_p2(out):
    p = REPO / "phase0" / "sensitivity" / "result.json"
    if not p.exists():
        return
    r = json.loads(p.read_text())
    fig, axs = plt.subplots(1, 2, figsize=(11, 5))
    for ax, (k, title) in zip(axs, (("cell_pce_pct", "cell PCE"), ("usd_per_W", "USD/W"))):
        rk = r["outputs"][k]["ranking"][:10][::-1]
        ax.barh([x["param"] for x in rk], [x["index"] for x in rk], xerr=[x["ci95_half"] for x in rk], color="tab:gray")
        nulls = [x for x in r["outputs"]["cell_pce_pct"]["ranking"] if x["param"].startswith("C")]
        ax.axvline(max(x["index"] + x["ci95_half"] for x in nulls), ls="--", color="tab:red", lw=1,
                   label="null ceiling (post-hoc)")
        ax.set_title(f"Borgonovo delta: {title} (top 10)", fontsize=10)
        ax.tick_params(axis="y", labelsize=8)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig5_p2_sensitivity.png", dpi=200)
    plt.close(fig)


def fig_schematic(out):
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    fig, ax = plt.subplots(figsize=(12.5, 2.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    labels = ["design vector\n(thicknesses,\nstripe width)", "schema check\n+ material\nlibrary", "SimSS\ndrift-diffusion\n(cell J-V)",
              "module model\n(GFF, TCO\nloss)", "factory cost\n(Malaysia,\nbottom-up)", "objectives\n(module PCE,\nUSD/W)"]
    w, gap, y, h = 0.135, 0.035, 0.45, 0.5
    xs = [0.01 + i * (w + gap) for i in range(len(labels))]
    for x, t in zip(xs, labels):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.005,rounding_size=0.02", fc="white", ec="k", lw=1))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=9, linespacing=1.15)
    for x in xs[:-1]:
        ax.add_patch(FancyArrowPatch((x + w, y + h / 2), (x + w + gap, y + h / 2), arrowstyle="-|>", mutation_scale=10, lw=1))
    # feedback loop: down from the last box, left along the bottom, up into the first box
    xl, xr, yb = xs[0] + w / 2, xs[-1] + w / 2, 0.2
    ax.plot([xr, xr, xl], [y, yb, yb], color="k", lw=1, ls="--")
    ax.add_patch(FancyArrowPatch((xl, yb), (xl, y), arrowstyle="-|>", mutation_scale=10, lw=1, ls="--"))
    ax.text((xl + xr) / 2, yb - 0.05, "optimiser proposes the next batch (Sobol random, NSGA-II or qNEHVI)",
            ha="center", va="top", fontsize=9)
    fig.savefig(out / "fig1_environment.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def tables(res, runs):
    L = ["# Paper A tables (generated by scripts/paperA_figures.py from phase0/paperA/result.json)", ""]
    L += ["## Q1: final hypervolume after 240 calls (mean ± 95% CI, 5 seeds)", "",
          "| Case | " + " | ".join(LABEL[m] for m in METHODS) + " | Verdicts (CI non-overlap) | Calls to 95% (median) | Unreliable |",
          "|---|" + "---|" * (len(METHODS) + 3)]
    for k, c in res["cases"].items():
        ms = c["methods"]
        v = [kk for kk, b in c["q1"].items() if b] or ["no difference found"]
        L.append(f"| {k} | " + " | ".join(f"{ms[m]['hv_mean']:.4g} ± {ms[m]['hv_ci95_half']:.2g}" for m in METHODS)
                 + f" | {', '.join(v)} | " + ", ".join(f"{m} {ms[m]['calls_to_95pct_best_median']}" for m in METHODS)
                 + f" | {'YES' if c['unreliable'] else 'no'} |")
    L += ["", "## Q2: efficiency–cost gap on the pooled front (Malaysia line)", "",
          "| Case | Front size | PCE-opt (module %, USD/W) | Cost-opt (module %, USD/W) | ΔPCE (pt) | ΔCost (%) | Small? |",
          "|---|---|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        q = c["q2"]
        p, o = q["pce_optimal"], q["cost_optimal"]
        L.append(f"| {k} | {q['front_size']} | {p['module_pce_pct']:.2f}, {p['usd_per_W']:.4f} | "
                 f"{o['module_pce_pct']:.2f}, {o['usd_per_W']:.4f} | {q['gap_pce_points']:.2f} | {q['gap_cost_pct']:.2f} | "
                 f"{'yes' if q['gap_small'] else 'no'} |")
    L += ["", "## Designs at the two ends of each front", "", "| Case | End | Design (nm, stripe mm) | Cell PCE % | Parts USD/W (mat / cap / opex) |",
          "|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        for which in ("pce_optimal", "cost_optimal"):
            d = c["q2"][which]
            pr = d["parts_usd_per_W"]
            L.append(f"| {k} | {which} | " + ", ".join(f"{n.replace('_nm', '').replace('_mm', '')} {v:g}" for n, v in d["x"].items())
                     + f" | {d['cell_pce_pct']:.2f} | {pr['materials']:.4f} / {pr['capital']:.4f} / {pr['other_opex']:.4f} |")
    L += ["", "## CN / IN capital-rate row (same designs; only the capital rate changed)", "",
          "| Case | End | MY | CN | IN |", "|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        for which in ("pce_optimal", "cost_optimal"):
            r = c["q2"][which]["usd_per_W_by_rate_region"]
            L.append(f"| {k} | {which} | {r['MY']:.4f} | {r['CN']:.4f} | {r['IN']:.4f} |")
    L += ["", "## Q3: robustness over the 3 scenarios", "", "| Stack | Q1 same in all | Some method beats random in all | Q1 robust | Absorber spread PCE-opt / cost-opt (fraction of range) | Designs robust |",
          "|---|---|---|---|---|---|"]
    for a, q in res["q3"].items():
        mv = q["absorber_move_frac_of_range"]
        L.append(f"| {a} | {q['q1_same_in_all_scenarios']} | {q['some_method_beats_random_in_all']} | {q['q1_robust']} | "
                 f"{mv['pce_optimal']:.2f} / {mv['cost_optimal']:.2f} | {q['designs_robust']} |")
    L += ["", "## Infeasible calls", "", "| Case | " + " | ".join(LABEL[m] for m in METHODS) + " | Reasons (all runs) |", "|---|---|---|---|---|"]
    for k, c in res["cases"].items():
        a, s = k.split("/")
        reasons = {}
        for m in METHODS:
            for kk in range(5):
                for cc in runs[(a, s, m, kk)]["calls"]:
                    if not cc["feasible"]:
                        key = (cc.get("reason") or cc.get("sim_status") or "?")[:40]
                        reasons[key] = reasons.get(key, 0) + 1
        L.append(f"| {k} | " + " | ".join(str(c["methods"][m]["n_infeasible"]) for m in METHODS)
                 + " | " + ("; ".join(f"{r} ×{n}" for r, n in sorted(reasons.items(), key=lambda t: -t[1])[:3]) or "none") + " |")
    n_calls = sum(len(r["calls"]) for r in runs.values())
    n_sec = sum(c.get("seconds") or 0 for r in runs.values() for c in r["calls"])
    L += ["", f"Total calls {n_calls} across {len(runs)} runs; summed SimSS seconds {n_sec:.0f} (cache hits count 0 s)."]
    return "\n".join(L) + "\n"


def main(out=None):
    out = Path(out) if out else A / "figures"
    out.mkdir(parents=True, exist_ok=True)
    res = json.loads((A / "result.json").read_text())
    runs = load(A / "runs")
    if len(runs) != 90:
        raise SystemExit(f"expected 90 runs, found {len(runs)}")
    fig_schematic(out)
    fig_hv(res, runs, out)
    fig_fronts(res, runs, out)
    fig_cost_parts(res, out)
    fig_p2(out)
    (out / "tables.md").write_text(tables(res, runs), encoding="utf-8")
    print("wrote", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
