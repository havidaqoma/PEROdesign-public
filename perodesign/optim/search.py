"""Paper A search methods and metrics (docs/PaperA_preregistration.md §5–§7).

Each method gets `evalf(U) -> list[(pce, usd) or None]`, where U is a list of unit-cube points and None marks an
infeasible design. Every point passed to evalf counts as one simulator call. Methods return the call log:
[{"call": i, "batch": b, "u": [...], "y": [pce, usd] | None}, ...] of length exactly `budget`.
"""
from __future__ import annotations

import math

import numpy as np

BUDGET, N_INIT, Q, POP = 240, 24, 12, 24


# ------------------------------------------------------------------ metrics
def pareto(points):
    """Non-dominated subset for (maximise pce, minimise usd). Input: list of (pce, usd). Keeps first of exact ties."""
    pts = sorted(set((float(p), float(c)) for p, c in points), key=lambda t: (-t[0], t[1]))
    front, best_c = [], math.inf
    for p, c in pts:
        if c < best_c:
            front.append((p, c))
            best_c = c
    return front


def hv2d(points, ref):
    """Exact 2-D hypervolume for (maximise pce, minimise usd) against ref = (pce_ref, usd_ref)."""
    pr, cr = ref
    f = [(p, c) for p, c in pareto(points) if p > pr and c < cr]
    f.sort(key=lambda t: t[1])                        # cheapest first -> pce increasing along the front
    hv, prev_p = 0.0, pr
    for p, c in f:
        if p > prev_p:
            hv += (p - prev_p) * (cr - c)
            prev_p = p
    return hv


def hv_curve(log, ref):
    pts, out = [], []
    for r in log:
        if r["y"] is not None:
            pts.append(tuple(r["y"]))
        out.append(hv2d(pts, ref))
    return out


# ------------------------------------------------------------------ methods
def sobol_points(d, n, seed):
    from scipy.stats import qmc
    m = max(1, math.ceil(math.log2(n)))
    return qmc.Sobol(d, scramble=True, seed=seed).random_base2(m)[:n]


def _log(U, Y, batch, start):
    return [{"call": start + i, "batch": batch, "u": [float(v) for v in u], "y": (None if y is None else list(y))}
            for i, (u, y) in enumerate(zip(U, Y))]


def run_random(evalf, d, seed, budget=BUDGET):
    U = sobol_points(d, budget, seed)
    log = []
    for b in range(0, budget, Q):                     # batches of Q only to keep progress visible
        chunk = [list(u) for u in U[b:b + Q]]
        log += _log(chunk, evalf(chunk), b // Q, b)
    return log


def run_nsga2(evalf, d, seed, ref, budget=BUDGET):
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.evaluator import Evaluator
    from pymoo.core.problem import Problem
    from pymoo.problems.static import StaticProblem
    problem = Problem(n_var=d, n_obj=2, n_ieq_constr=1, xl=0.0, xu=1.0)
    algo = NSGA2(pop_size=POP, sampling=sobol_points(d, N_INIT, seed))
    algo.setup(problem, seed=seed, verbose=False)
    log, batch = [], 0
    while len(log) < budget:
        pop = algo.ask()
        X = pop.get("X")[: budget - len(log)]
        pop = pop[: len(X)]
        U = [list(map(float, x)) for x in X]
        Y = evalf(U)
        F = np.array([[-ref[0], ref[1]] if y is None else [-y[0], y[1]] for y in Y], float)
        G = np.array([[1.0] if y is None else [-1.0] for y in Y], float)
        Evaluator().eval(StaticProblem(problem, F=F, G=G), pop)
        algo.tell(infills=pop)
        log += _log(U, Y, batch, len(log))
        batch += 1
    return log


def infeasible_fill(log, ref):
    """Value given to infeasible points in the BO model: the worst FEASIBLE value seen so far on each objective
    (lowest PCE, highest USD/W); the reference point only if nothing is feasible yet. Imputing the reference point
    itself put a ~38 USD/W outlier into the n-i-p cost GP (agy review 2026-09-30)."""
    ys = [r["y"] for r in log if r["y"] is not None]
    if not ys:
        return ref[0], ref[1]
    return min(y[0] for y in ys), max(y[1] for y in ys)


def run_qnehvi(evalf, d, seed, ref, budget=BUDGET, q=Q, restarts=4, raw=256, mc=64):
    import torch
    from botorch.acquisition.multi_objective.logei import qLogNoisyExpectedHypervolumeImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import ModelListGP, SingleTaskGP
    from botorch.models.transforms.outcome import Standardize
    from botorch.optim import optimize_acqf
    from botorch.sampling.normal import SobolQMCNormalSampler
    from gpytorch.mlls.sum_marginal_log_likelihood import SumMarginalLogLikelihood
    torch.set_num_threads(1)
    tkw = {"dtype": torch.double}
    ref_t = torch.tensor([ref[0], -ref[1]], **tkw)      # botorch maximises: (pce, -usd)
    U0 = [list(map(float, u)) for u in sobol_points(d, N_INIT, seed)]
    log = _log(U0, evalf(U0), 0, 0)
    bounds = torch.stack([torch.zeros(d, **tkw), torch.ones(d, **tkw)])
    batch = 1
    while len(log) < budget:
        torch.manual_seed(seed * 1000 + batch)
        fp, fc = infeasible_fill(log, ref)
        X = torch.tensor([r["u"] for r in log], **tkw)
        Y = torch.tensor([[fp, -fc] if r["y"] is None else [r["y"][0], -r["y"][1]] for r in log], **tkw)
        models = [SingleTaskGP(X, Y[:, i:i + 1], outcome_transform=Standardize(m=1)) for i in range(2)]
        model = ModelListGP(*models)
        fit_gpytorch_mll(SumMarginalLogLikelihood(model.likelihood, model))
        acq = qLogNoisyExpectedHypervolumeImprovement(
            model=model, ref_point=ref_t, X_baseline=X, prune_baseline=True,
            sampler=SobolQMCNormalSampler(sample_shape=torch.Size([mc]), seed=seed * 1000 + batch))
        n = min(q, budget - len(log))
        cand, _ = optimize_acqf(acq, bounds=bounds, q=n, num_restarts=restarts, raw_samples=raw, sequential=True,
                                options={"batch_limit": 5, "maxiter": 200})
        U = [[min(max(float(v), 0.0), 1.0) for v in row] for row in cand.detach().cpu().numpy()]
        log += _log(U, evalf(U), batch, len(log))
        batch += 1
    return log


METHODS = {"random": run_random, "nsga2": run_nsga2, "qnehvi": run_qnehvi}


def run_method(method, evalf, d, seed, ref, budget=BUDGET):
    if method == "random":
        log = run_random(evalf, d, seed, budget)
    else:
        log = METHODS[method](evalf, d, seed, ref, budget)
    if len(log) != budget:
        raise RuntimeError(f"{method}: {len(log)} calls, budget {budget}")
    return log


def t_ci95(xs):
    """Mean and 95% t half-width (n-1 dof)."""
    from scipy import stats
    x = np.asarray(xs, float)
    if len(x) < 2:
        return float(x.mean()), float("nan")
    return float(x.mean()), float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x)))
