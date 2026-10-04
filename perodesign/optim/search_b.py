"""Paper B search methods (docs/PaperB_preregistration.md §5). Paper A's search.py is reused for the metrics
(pareto, hv2d, hv_curve, t_ci95) and the Sobol generator; nothing in it is changed.

A point is a unit vector of length n_cont + n_cat. The last n_cat coordinates encode categories: in the call log
they are stored as the category index (0..K-1), and evalf receives (u_cont, cats). Objectives passed back by evalf:
(module PCE %, log10 USD/W) or None for an infeasible call. Every call to evalf counts against the budget.

Methods:
  random   Sobol in n_cont + n_cat dims, categories by the relaxed decoding (objective_b.decode_relaxed)
  nsga2    pymoo MixedVariableGA with NSGA-II survival (Choice + Real variables), population 24
  mixbo    BoTorch qLogNEHVI on MixedSingleTaskGP (categorical kernel on the category dims), acquisition optimised by
           exact enumeration over the material combinations (amendment A1); infeasible = worst feasible so far
"""
from __future__ import annotations

import numpy as np

from . import search as SA
from .objective_b import decode_relaxed

BUDGET, N_INIT, Q, POP = 240, 24, 12, 24
pareto, hv2d, hv_curve, t_ci95 = SA.pareto, SA.hv2d, SA.hv_curve, SA.t_ci95


def _log(points, Y, batch, start):
    return [{"call": start + i, "batch": batch, "u": [float(v) for v in uc], "cats": [int(c) for c in cats],
             "y": (None if y is None else list(y))} for i, ((uc, cats), y) in enumerate(zip(points, Y))]


def initial_points(sp, n, seed):
    """First n points shared by all methods: Sobol in n_cont + n_cat dims, relaxed decoding of the categories."""
    U = SA.sobol_points(sp.dim, n, seed)
    return [decode_relaxed(sp, u) for u in U]


def run_random(evalf, sp, seed, budget=BUDGET):
    P = initial_points(sp, budget, seed)
    log = []
    for b in range(0, budget, Q):
        chunk = P[b:b + Q]
        log += _log(chunk, evalf(chunk), b // Q, b)
    return log


def run_nsga2(evalf, sp, seed, ref, budget=BUDGET):
    from pymoo.algorithms.moo.nsga2 import RankAndCrowding
    from pymoo.core.evaluator import Evaluator
    from pymoo.core.mixed import MixedVariableGA
    from pymoo.core.population import Population
    from pymoo.core.problem import Problem
    from pymoo.core.variable import Choice, Real
    from pymoo.problems.static import StaticProblem

    vars_ = {f"c{i}": Real(bounds=(0.0, 1.0)) for i in range(sp.n_cont)}
    vars_.update({f"k{j}": Choice(options=list(range(K))) for j, K in enumerate(sp.cat_sizes)})
    problem = Problem(vars=vars_, n_obj=2, n_ieq_constr=1)

    def to_point(xd):
        return [float(xd[f"c{i}"]) for i in range(sp.n_cont)], [int(xd[f"k{j}"]) for j in range(sp.n_cat)]

    P0 = initial_points(sp, N_INIT, seed)
    X0 = [{**{f"c{i}": float(uc[i]) for i in range(sp.n_cont)}, **{f"k{j}": int(c[j]) for j in range(sp.n_cat)}}
          for uc, c in P0]
    algo = MixedVariableGA(pop_size=POP, sampling=Population.new(X=np.array(X0, dtype=object)),
                           survival=RankAndCrowding())
    algo.setup(problem, seed=seed, verbose=False)
    log, batch = [], 0
    while len(log) < budget:
        pop = algo.ask()
        pop = pop[: budget - len(log)]
        pts = [to_point(x) for x in pop.get("X")]
        Y = evalf(pts)
        F = np.array([[-ref[0], ref[1]] if y is None else [-y[0], y[1]] for y in Y], float)
        G = np.array([[1.0] if y is None else [-1.0] for y in Y], float)
        Evaluator().eval(StaticProblem(problem, F=F, G=G), pop)
        algo.tell(infills=pop)
        log += _log(pts, Y, batch, len(log))
        batch += 1
    return log


def _enc(sp, uc, cats):
    """Model input: continuous unit coords, then category indices as floats (MixedSingleTaskGP cat_dims)."""
    return list(uc) + [float(c) for c in cats]


def run_mixbo(evalf, sp, seed, ref, budget=BUDGET, q=Q, restarts=4, raw=256, mc=64, isolate=None):
    """Amendment A1 (prereg §10): the acquisition is maximised by EXACT ENUMERATION over the material combinations
    (optimize_acqf_mixed with one fixed_features dict per combination, sequential greedy over q), each with Paper A's
    continuous L-BFGS settings (4 restarts, 256 raw samples, batch_limit 5, maxiter 200). Replaces the alternating
    local search, which took ~40 min per batch at n~130 (py-spy: all time in the acquisition optimiser).
    Amendment A3: each step (fit + acquisition) runs in a short-lived child process (perodesign.optim.bo_step), because
    in-process memory grew ~1.4 GB per step. Same computation, same seeds; isolate=False runs it in-process (tests
    check both give identical candidates). Default: env PAPERB_BO_ISOLATE (1)."""
    import os

    from .bo_step import bo_step, run_isolated
    if isolate is None:
        isolate = os.environ.get("PAPERB_BO_ISOLATE", "1") == "1"
    P0 = initial_points(sp, N_INIT, seed)
    log = _log(P0, evalf(P0), 0, 0)
    cat_idx = list(range(sp.n_cont, sp.dim))
    batch = 1
    while len(log) < budget:
        fp, fc = SA.infeasible_fill(log, ref)
        spec = {"X": [_enc(sp, r["u"], r["cats"]) for r in log],
                "Y": [[fp, -fc] if r["y"] is None else [r["y"][0], -r["y"][1]] for r in log],
                "cat_idx": cat_idx, "cat_sizes": list(sp.cat_sizes), "n_cont": sp.n_cont,
                "ref": [ref[0], -ref[1]], "q": min(q, budget - len(log)), "restarts": restarts, "raw": raw, "mc": mc,
                "seed": seed * 1000 + batch}
        cand = run_isolated(spec) if isolate else bo_step(spec)
        pts = []
        for row in cand:
            uc = [min(max(float(v), 0.0), 1.0) for v in row[:sp.n_cont]]
            cats = [int(round(float(v))) for v in row[sp.n_cont:]]
            if any(not 0 <= c < K for c, K in zip(cats, sp.cat_sizes)):
                raise RuntimeError(f"mixbo proposed an out-of-range category {cats}")
            pts.append((uc, cats))
        log += _log(pts, evalf(pts), batch, len(log))
        batch += 1
    return log


METHODS = {"random": run_random, "nsga2": run_nsga2, "mixbo": run_mixbo}


def run_method(method, evalf, sp, seed, ref, budget=BUDGET):
    log = run_random(evalf, sp, seed, budget) if method == "random" else METHODS[method](evalf, sp, seed, ref, budget)
    if len(log) != budget:
        raise RuntimeError(f"{method}: {len(log)} calls, budget {budget}")
    return log
