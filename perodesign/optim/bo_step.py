"""One mixed-BO step (Paper B, amendment A3): fit the two MixedSingleTaskGP models and maximise qLogNEHVI by exact
enumeration over the material combinations. Pure function of its JSON input, so it can run in-process or in a
short-lived child process (python -m perodesign.optim.bo_step < in.json > out.json). The child process returns all
its memory to the OS when it exits; in-process, memory grew ~1.4 GB per step (measured) and OOM-killed the batch.

Input JSON: {"X": [[...]], "Y": [[...]], "cat_idx": [...], "cat_sizes": [...], "n_cont": int, "ref": [pce, -log10usd],
             "q": int, "restarts": int, "raw": int, "mc": int, "seed": int}   (seed = torch seed = sampler seed)
Output JSON: {"cand": [[...]]}   (floats; json round-trips Python floats exactly)
"""
from __future__ import annotations

import itertools
import json
import sys


def bo_step(spec: dict) -> list[list[float]]:
    import torch
    from botorch.acquisition.multi_objective.logei import qLogNoisyExpectedHypervolumeImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import MixedSingleTaskGP, ModelListGP
    from botorch.models.transforms.outcome import Standardize
    from botorch.optim import optimize_acqf_mixed
    from botorch.sampling.normal import SobolQMCNormalSampler
    from gpytorch.mlls.sum_marginal_log_likelihood import SumMarginalLogLikelihood
    torch.set_num_threads(1)
    tkw = {"dtype": torch.double}
    torch.manual_seed(spec["seed"])
    X = torch.tensor(spec["X"], **tkw)
    Y = torch.tensor(spec["Y"], **tkw)
    cat_idx, sizes, nc = list(spec["cat_idx"]), list(spec["cat_sizes"]), int(spec["n_cont"])
    d = nc + len(cat_idx)
    bounds = torch.stack([torch.zeros(d, **tkw), torch.tensor([1.0] * nc + [float(K - 1) for K in sizes], **tkw)])
    fixed = [{i: float(v) for i, v in zip(cat_idx, combo)} for combo in itertools.product(*[range(K) for K in sizes])]
    models = [MixedSingleTaskGP(X, Y[:, i:i + 1], cat_dims=cat_idx, outcome_transform=Standardize(m=1)) for i in range(2)]
    model = ModelListGP(*models)
    fit_gpytorch_mll(SumMarginalLogLikelihood(model.likelihood, model))
    acq = qLogNoisyExpectedHypervolumeImprovement(
        model=model, ref_point=torch.tensor(spec["ref"], **tkw), X_baseline=X, prune_baseline=True,
        sampler=SobolQMCNormalSampler(sample_shape=torch.Size([spec["mc"]]), seed=spec["seed"]))
    cand, _ = optimize_acqf_mixed(acq, bounds=bounds, q=spec["q"], num_restarts=spec["restarts"],
                                  raw_samples=spec["raw"], fixed_features_list=fixed,
                                  options={"batch_limit": 5, "maxiter": 200})
    return [[float(v) for v in row] for row in cand.detach().cpu().tolist()]


def run_isolated(spec: dict, timeout_s: float = 7200.0) -> list[list[float]]:
    """bo_step in a fresh Python process (same interpreter, same environment)."""
    import subprocess
    p = subprocess.run([sys.executable, "-m", "perodesign.optim.bo_step"], input=json.dumps(spec), text=True,
                       capture_output=True, timeout=timeout_s)
    if p.returncode != 0:
        raise RuntimeError(f"bo_step child failed rc={p.returncode}: {p.stderr[-2000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])["cand"]


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    print(json.dumps({"cand": bo_step(json.loads(sys.stdin.read()))}))
