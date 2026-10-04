"""SIMsalabim SimSS v5.36 wrapper: validated design -> one steady-state J-V simulation -> result record.

Contract (plan v2 s5.1, Phase 0 findings):
  * Input is ONLY a schema-v1 design (perodesign.schema.validate). EVERY physics, device and solver
    parameter in the SimSS template files is passed explicitly on the command line from the library
    (layers, interfaces, device_setup). __init__ parses the template files and refuses to start if
    any template parameter is neither passed nor on the NOT_PASSED list of pure file-name/IO keys.
  * Fixed solver settings: -Vmax 1.4 (default 1.24 V is below good Voc), -varFile none, -untilVoc 1.
  * Every run happens in a FRESH directory; result files are never reused (Phase 0 stale-file bug).
  * Metrics are parsed from STDOUT. The PCE comes from the MPP line. It is trusted only when the
    maximum is BRACKETED: >= 2 converged points below Vmpp and >= 2 CONTIGUOUS converged points
    above it, i.e. between Vmpp and the first non-converged voltage (Phase 0 mpp_trust: 18/18
    bracketed runs matched a 2x finer sweep to 0.04%).
  * status: "complete" = all of Jsc/Voc/FF/MPP;  "partial" = MPP trusted, Voc/FF missing (never
    guessed);  "failed" = no trustworthy MPP, or a sanity gate failed. Every failure has a reason.
  * PCE = MPP / 1000 W m^-2 (1-sun AM1.5G incident power; assumption recorded in every result).
Result schema: perodesign.simresult/1 (see SimResult).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..library import load_library
from ..schema import design_hash, resolved_layers, validate

RESULT_SCHEMA = "perodesign.simresult/1"
SIMSS_VERSION = "5.36"
SOLVER_ARGS = ["-Vmax", "1.4", "-varFile", "none", "-untilVoc", "1"]
# p-i-n (anode left) must sweep DOWN (SimSS rule leftElec x Vscan < 0); a downward sweep that stops at Voc
# never reaches the MPP, so p-i-n runs the full sweep (untilVoc 0). Same Vmax, same step.
SOLVER_ARGS_BY_ARCH = {"p-i-n": ["-Vmax", "1.4", "-varFile", "none", "-untilVoc", "0"]}
INCIDENT_W_M2 = 1000.0
PCE_MAX_SANITY_PCT = 33.7 * 1.05   # SQ-limit gate (scaps-device-protocol s5): above this = not physical
MIN_CONVERGED_ABOVE_VMPP = 2
MIN_CONVERGED_BELOW_VMPP = 2

# library key (unit in the name) -> SimSS parameter name. Explicit table: an unmapped library key is
# an error, never passed through by string manipulation.
LAYER_KEYMAP = {
    "eps_r": "eps_r", "E_c_eV": "E_c", "E_v_eV": "E_v", "N_c_m3": "N_c", "N_D_m3": "N_D", "N_A_m3": "N_A",
    "mu_n_m2_Vs": "mu_n", "mu_p_m2_Vs": "mu_p", "N_anion_m3": "N_anion", "N_cation_m3": "N_cation",
    "mu_anion_m2_Vs": "mu_anion", "mu_cation_m2_Vs": "mu_cation", "ionsMayEnter": "ionsMayEnter",
    "layerGen": "layerGen", "k_direct_m3_s": "k_direct", "N_t_bulk_m3": "N_t_bulk",
    "C_n_bulk_m3_s": "C_n_bulk", "C_p_bulk_m3_s": "C_p_bulk", "E_t_bulk_eV": "E_t_bulk",
    "bulkTrapType": "bulkTrapType", "nk_file": "nkLayer",
    "mobnDep": "mobnDep", "mobpDep": "mobpDep", "gamma_n_sqrt_m_V": "gamma_n", "gamma_p_sqrt_m_V": "gamma_p",
    "G_ehp_per_m3_s": "G_ehp", "fieldDepG": "fieldDepG", "P0": "P0", "a_m": "a", "thermLengDist": "thermLengDist",
    "k_f_per_s": "k_f", "preLangevin": "preLangevin", "useLangevin": "useLangevin", "bulkTrapFile": "bulkTrapFile",
}
INTERFACE_KEYMAP = {
    "nu_int_n_m_s": "nu_int_n", "nu_int_p_m_s": "nu_int_p", "N_t_int_m2": "N_t_int",
    "E_t_int_eV": "E_t_int", "intTrapType": "intTrapType", "C_n_int_m3_s": "C_n_int",
    "C_p_int_m3_s": "C_p_int", "intTrapFile": "intTrapFile",
}
SETUP_KEYMAP = {
    "T_K": "T", "leftElec": "leftElec", "W_L_eV": "W_L", "W_R_eV": "W_R", "S_n_L_m_s": "S_n_L",
    "S_p_L_m_s": "S_p_L", "S_n_R_m_s": "S_n_R", "S_p_R_m_s": "S_p_R", "R_shunt_Ohm_m2": "R_shunt",
    "R_series_Ohm_m2": "R_series", "G_frac": "G_frac", "genProfile": "genProfile", "L_TCO_m": "L_TCO",
    "L_BE_m": "L_BE", "nkSubstrate_file": "nkSubstrate", "nkTCO_file": "nkTCO", "nkBE_file": "nkBE",
    "spectrum_file": "spectrum", "lambda_min_m": "lambda_min", "lambda_max_m": "lambda_max", "NP": "NP",
    "tolPois_V": "tolPois", "maxDelV": "maxDelV", "maxItPois": "maxItPois", "maxItSS": "maxItSS",
    "currDiffInt": "currDiffInt", "tolCurr": "tolCurr", "tolDens": "tolDens", "couplePC": "couplePC",
    "minAcc": "minAcc", "maxAcc": "maxAcc", "ignoreNegDens": "ignoreNegDens", "convVar": "convVar",
    "failureMode": "failureMode", "grad": "grad", "Vdist": "Vdist", "preCond": "preCond", "Vpre_V": "Vpre",
    "fixIons": "fixIons", "Vscan": "Vscan", "Vmin_V": "Vmin", "Vstep_V": "Vstep", "Vacc_V": "Vacc",
    "NJV": "NJV", "timeout_s": "timeout", "pauseAtEnd": "pauseAtEnd", "useExpData": "useExpData",
    "limitDigits": "limitDigits",
}
# Data-file keys: value is a file name inside the SimSS Data dir -> absolute path, must exist.
FILE_KEYS = {"nk_file", "nkSubstrate_file", "nkTCO_file", "nkBE_file", "spectrum_file"}
# Optical-constant files added by PeroDesign (not shipped with SIMsalabim) live here; a file name is looked up
# in the SimSS Data dir first, then here. Both are hashed into the cache key.
EXTRA_NK_DIR = Path(__file__).resolve().parents[2] / "data" / "nk"
# SimSS template for layers beyond the 3 shipped files: layer 4+ reuse L3's FILE STRUCTURE only; every value is
# overridden on the command line (the inheritance check below covers the L3 template keys).
MAX_LAYERS = 6
# Template keys deliberately NOT passed: layer-file names, output/IO file names and fitting options
# (no effect on the simulated J-V), plus the 3 solver-policy flags that SOLVER_ARGS sets.
NOT_PASSED = {"l1", "l2", "l3", "expJV", "fitMode", "fitThreshold", "JVFile", "varFile", "outputRatio",
              "scParsFile", "logFile", "autoTidy", "Vmax", "untilVoc"}
TEMPLATE_FILES = ["simulation_setup.txt", "L1_parameters.txt", "L2_parameters.txt", "L3_parameters.txt"]


class SimSSConfigError(RuntimeError):
    pass


def _default_dirs() -> tuple[Path, Path, str]:
    """(SimSS dir with binary + template files, Data dir, binary name). Point PERODESIGN_SIMSALABIM at the root of a
    SIMsalabim 5.36 checkout (the folder holding SimSS/ and Data/), or set PERODESIGN_SIMSS_DIR / PERODESIGN_SIMSS_DATA
    directly. The fallback is the location used for the published runs."""
    win = platform.system() == "Windows"
    root = os.environ.get("PERODESIGN_SIMSALABIM")
    base = Path(root) if root else (Path("F:/SIMsalabim/src") if win else Path("/mnt/f/SIMsalabim/src"))
    sim = Path(os.environ.get("PERODESIGN_SIMSS_DIR", base / "SimSS"))
    data = Path(os.environ.get("PERODESIGN_SIMSS_DATA", base / "Data"))
    return sim, data, ("simss.exe" if win else "simss")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _template_keys(path: Path) -> list[str]:
    keys = []
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r"^([A-Za-z_]\w*)\s*=", line)
        if m:
            keys.append(m.group(1))
    return keys


def _fmt(v) -> str:
    if isinstance(v, bool):
        raise TypeError("bool is not a SimSS value")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.6e}"
    return str(v)


@dataclass
class SimResult:
    schema: str
    status: str                      # complete | partial | failed
    reason: str | None               # why partial/failed (None for complete)
    design_hash: str
    design: dict                     # normalised, validated design
    metrics: dict                    # pce_pct, jsc_mA_cm2, voc_V, ff, vmpp_V, mpp_W_m2 (None if missing)
    convergence: dict                # n_converged, n_nonconverged, first_nonconv_V, n_conv_above_vmpp
    returncode: int | None
    seconds: float | None
    provenance: dict                 # simss version, binary sha256, library version + sha256, args, assumptions
    warnings: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


_NUM = r"(-?[\d.]+(?:[eE][+-]?\d+)?)"


def parse_stdout(text: str) -> dict:
    """Parse SimSS v5.36 stdout. Pure function (tested on captured real outputs)."""
    g = lambda k: (re.search(rf"^{k}:\s+{_NUM}", text, re.M) or [None, None])[1]
    jsc, vmpp, mpp, voc, ff = g("Jsc"), g("Vmpp"), g("MPP"), g("Voc"), g("FF")
    conv = [float(v) for v in re.findall(rf"At Vint=\s*{_NUM} converged", text)]
    nonconv = [float(v) for v in re.findall(rf"No convergence for Vint=\s*{_NUM}", text)]
    out = {
        "jsc_A_m2": float(jsc) if jsc else None, "vmpp_V": float(vmpp) if vmpp else None,
        "mpp_W_m2": float(mpp) if mpp else None, "voc_V": float(voc) if voc else None,
        "ff": float(ff) if ff else None,
        "could_not_determine": "Could not determine" in text,
        "finished": "Finished" in text,
        "n_converged": len(conv), "n_nonconverged": len(nonconv),
        "first_nonconv_V": min(nonconv) if nonconv else None,
    }
    vm, fn = out["vmpp_V"], out["first_nonconv_V"]
    # contiguous converged points ABOVE Vmpp: only those below the first non-converged voltage count
    out["n_conv_above_vmpp"] = (sum(1 for v in conv if v > vm and (fn is None or v < fn)) if vm is not None else 0)
    out["n_conv_below_vmpp"] = sum(1 for v in conv if v < vm) if vm is not None else 0
    out["nonconv_below_vmpp"] = bool(vm is not None and fn is not None and fn <= vm)
    return out


def classify(parsed: dict) -> tuple[str, str | None, dict, list]:
    """parsed stdout -> (status, reason, metrics, warnings). Pure function."""
    warnings: list[str] = []
    mpp, jsc = parsed["mpp_W_m2"], parsed["jsc_A_m2"]
    metrics = {"pce_pct": None, "jsc_mA_cm2": None, "voc_V": None, "ff": None,
               "vmpp_V": parsed["vmpp_V"], "mpp_W_m2": mpp}
    if mpp is None:
        return "failed", "no MPP line in SimSS stdout", metrics, warnings
    if parsed["vmpp_V"] is None or parsed["vmpp_V"] <= 0:
        return "failed", f"Vmpp {parsed['vmpp_V']} V not positive", metrics, warnings
    if parsed.get("nonconv_below_vmpp"):
        return ("failed", f"non-converged point at {parsed['first_nonconv_V']} V <= Vmpp={parsed['vmpp_V']} V",
                metrics, warnings)
    if parsed["n_conv_above_vmpp"] < MIN_CONVERGED_ABOVE_VMPP:
        return ("failed", f"MPP not bracketed: {parsed['n_conv_above_vmpp']} contiguous converged points above "
                f"Vmpp={parsed['vmpp_V']} V (need >= {MIN_CONVERGED_ABOVE_VMPP})", metrics, warnings)
    if parsed.get("n_conv_below_vmpp", 0) < MIN_CONVERGED_BELOW_VMPP:
        return ("failed", f"MPP not bracketed: {parsed.get('n_conv_below_vmpp', 0)} converged points below "
                f"Vmpp={parsed['vmpp_V']} V (need >= {MIN_CONVERGED_BELOW_VMPP})", metrics, warnings)
    pce = mpp / INCIDENT_W_M2 * 100.0
    if not 0.0 < pce <= PCE_MAX_SANITY_PCT:
        return "failed", f"PCE {pce:.3f}% outside (0, {PCE_MAX_SANITY_PCT:.2f}] sanity gate", metrics, warnings
    metrics["pce_pct"] = pce
    if jsc is not None:
        metrics["jsc_mA_cm2"] = -jsc / 10.0      # SimSS: A/m2, negative = generating
        if metrics["jsc_mA_cm2"] <= 0:
            return "failed", f"non-generating Jsc {jsc} A/m2", metrics, warnings
    if jsc is None:
        warnings.append("no Jsc line in SimSS stdout")
        return "partial", "Jsc missing from stdout; MPP bracketed", metrics, warnings
    if parsed["could_not_determine"] or parsed["voc_V"] is None or parsed["ff"] is None:
        warnings.append("SimSS could not determine all solar-cell parameters; Voc/FF left missing")
        return "partial", "Voc/FF not determined (solver stalled between MPP and Voc); MPP bracketed", metrics, warnings
    metrics["voc_V"], metrics["ff"] = parsed["voc_V"], parsed["ff"]
    if not 0.0 < metrics["ff"] <= 1.0:
        return "failed", f"FF {metrics['ff']} outside (0, 1]", metrics, warnings
    if not 0.0 < parsed["vmpp_V"] < metrics["voc_V"]:
        return "failed", f"need 0 < Vmpp < Voc, got Vmpp={parsed['vmpp_V']} Voc={metrics['voc_V']}", metrics, warnings
    return "complete", None, metrics, warnings


class SimSS:
    """One configured SimSS installation. Thread-safe: each run uses its own temp dir."""

    def __init__(self, simss_dir: str | Path | None = None, data_dir: str | Path | None = None,
                 work_root: str | Path | None = None, library: dict | None = None,
                 timeout_s: float = 300.0, cache_dir: str | Path | None = None, contact_scenario: str = "ideal"):
        d_sim, d_data, exe = _default_dirs()
        self.simss_dir = Path(simss_dir) if simss_dir else d_sim
        self.data_dir = Path(data_dir) if data_dir else d_data
        self.binary = self.simss_dir / exe
        self.work_root = Path(work_root) if work_root else Path(tempfile.gettempdir())
        self.library = library or load_library()
        self.timeout_s = timeout_s
        self.cache_dir = Path(cache_dir) if cache_dir else None
        scen = (self.library.get("contact_scenarios") or {"ideal": {}})
        if contact_scenario not in scen:
            raise SimSSConfigError(f"contact_scenario {contact_scenario!r} not in library {sorted(scen)}")
        self.contact_scenario = contact_scenario
        for p in [self.binary, self.data_dir] + [self.simss_dir / f for f in TEMPLATE_FILES]:
            if not p.exists():
                raise SimSSConfigError(f"SimSS file missing: {p}")
        head = (self.simss_dir / "simulation_setup.txt").read_text(errors="replace")[:400]
        if f"version: {SIMSS_VERSION}" not in head:
            raise SimSSConfigError(f"template is not SimSS {SIMSS_VERSION}: {self.simss_dir}")
        self.binary_sha256 = _sha256_file(self.binary)
        # Refuse to run if any template parameter would be inherited silently.
        passed_layer = set(LAYER_KEYMAP.values()) | set(INTERFACE_KEYMAP.values()) | {"L"}
        passed_setup = set(SETUP_KEYMAP.values())
        missing = []
        for f in TEMPLATE_FILES[1:]:
            missing += [f"{f}:{k}" for k in _template_keys(self.simss_dir / f) if k not in passed_layer]
        missing += [f"simulation_setup.txt:{k}" for k in _template_keys(self.simss_dir / "simulation_setup.txt")
                    if k not in passed_setup and k not in NOT_PASSED]
        if missing:
            raise SimSSConfigError(f"template parameters not passed explicitly (would be inherited): {missing}")
        setup = (self.library.get("device_setup") or {}).get("params")
        if not setup or set(setup) != set(SETUP_KEYMAP):
            raise SimSSConfigError("library device_setup.params must contain exactly the SETUP_KEYMAP keys; "
                                   f"diff: {sorted(set(setup or {}) ^ set(SETUP_KEYMAP))}")
        # Everything that can change a result goes into the cache key.
        files = {f: _sha256_file(self.simss_dir / f) for f in TEMPLATE_FILES}
        used = {v for L in self.library["materials"].values() for k, v in L["params"].items() if k in FILE_KEYS}
        used |= {v for k, v in setup.items() if k in FILE_KEYS}
        for arch_over in (self.library.get("architecture_setup") or {}).values():
            unknown = set(arch_over) - set(SETUP_KEYMAP)
            if unknown:
                raise SimSSConfigError(f"architecture_setup has unknown keys {sorted(unknown)}")
            used |= {v for k, v in arch_over.items() if k in FILE_KEYS}
        for name in sorted(used):
            fp = self._data_file(name)
            files[f"Data/{name}"] = _sha256_file(fp)
        self.input_files_sha256 = files

    def _data_file(self, name: str) -> Path:
        for d in (self.data_dir, EXTRA_NK_DIR):
            if (d / name).exists():
                return d / name
        raise SimSSConfigError(f"data file missing: {name} (looked in {self.data_dir} and {EXTRA_NK_DIR})")

    def device_setup(self, architecture: str) -> dict:
        """Library device_setup with the architecture's overrides applied (p-i-n: anode left, sfb, Cu)."""
        s = dict(self.library["device_setup"]["params"])
        s.update((self.library.get("architecture_setup") or {}).get(architecture, {}))
        over = ((self.library.get("contact_scenarios") or {}).get(self.contact_scenario) or {}).get(architecture, {})
        unknown = set(over) - set(SETUP_KEYMAP)
        if unknown:
            raise SimSSConfigError(f"contact scenario sets unknown keys {sorted(unknown)}")
        s.update(over)
        return s

    # ------------------------------------------------------------------ mapping
    def _val(self, k, v):
        if k in FILE_KEYS:
            return self._data_file(v).as_posix()
        return _fmt(v)

    def build_args(self, design: dict) -> list[str]:
        """Validated design -> full SimSS CLI override list (excluding the binary)."""
        layers = resolved_layers(design, self.library)
        if len(layers) > MAX_LAYERS:
            raise SimSSConfigError(f"{len(layers)} layers > MAX_LAYERS {MAX_LAYERS}")
        arch = validate(design, self.library)["architecture"]
        args: list[str] = []
        for k, v in self.device_setup(arch).items():
            args += [f"-{SETUP_KEYMAP[k]}", self._val(k, v)]
        for i, L in enumerate(layers, start=1):
            args += [f"-l{i}.L", _fmt(float(L["thickness_nm"]) * 1e-9)]
            for k, v in L["params"].items():
                if k not in LAYER_KEYMAP:
                    raise SimSSConfigError(f"library layer key '{k}' has no SimSS mapping")
                args += [f"-l{i}.{LAYER_KEYMAP[k]}", self._val(k, v)]
            for k, v in (L["interface_right"] or {}).items():
                if k not in INTERFACE_KEYMAP:
                    raise SimSSConfigError(f"library interface key '{k}' has no SimSS mapping")
                args += [f"-l{i}.{INTERFACE_KEYMAP[k]}", _fmt(v)]
        return args + SOLVER_ARGS_BY_ARCH.get(arch, SOLVER_ARGS)

    def _prepare_dir(self, n_layers: int) -> Path:
        self.work_root.mkdir(parents=True, exist_ok=True)
        wd = Path(tempfile.mkdtemp(prefix="simss_", dir=self.work_root))
        def _fix(txt):
            return (txt.replace("../Data/", self.data_dir.as_posix() + "/")
                    .replace("..\\Data\\", self.data_dir.as_posix() + "/"))
        setup = _fix((self.simss_dir / "simulation_setup.txt").read_text(errors="replace"))
        # declare exactly n_layers layer files (l1..lN); the shipped setup lists l1..l3
        lines = [ln for ln in setup.splitlines() if not re.match(r"^l\d+\s*=", ln)]
        at = next(i for i, ln in enumerate(setup.splitlines()) if re.match(r"^l1\s*=", ln))
        decl = [f"l{i} = L{i}_parameters.txt                        * parameter file for layer {i}" for i in range(1, n_layers + 1)]
        (wd / "simulation_setup.txt").write_text("\n".join(lines[:at] + decl + lines[at:]) + "\n", newline="\n")
        for i in range(1, n_layers + 1):
            src = self.simss_dir / f"L{min(i, 3)}_parameters.txt"
            (wd / f"L{i}_parameters.txt").write_text(_fix(src.read_text(errors="replace")), newline="\n")
        for stale in ("scPars.txt", "JV.dat", "log.txt", "Var.dat", "none"):
            (wd / stale).unlink(missing_ok=True)
        return wd

    def _cache_key(self, dh: str) -> str:
        blob = json.dumps([dh, self.library["_sha256"], self.binary_sha256, SOLVER_ARGS, SOLVER_ARGS_BY_ARCH,
                           self.contact_scenario,
                           sorted(self.input_files_sha256.items())])
        return hashlib.sha256(blob.encode()).hexdigest()

    # ------------------------------------------------------------------ run
    def run(self, design: dict) -> SimResult:
        norm = validate(design, self.library)          # raises DesignError: invalid designs never run
        dh = design_hash(norm, self.library)
        key = self._cache_key(dh)
        if self.cache_dir:
            cp = self.cache_dir / f"{key}.json"
            if cp.exists():
                try:
                    return SimResult(**json.loads(cp.read_text()))
                except (json.JSONDecodeError, TypeError, OSError):
                    pass            # unreadable / partial cache entry: ignore and re-simulate
        args = self.build_args(norm)
        prov = {"simss_version": SIMSS_VERSION, "binary": str(self.binary), "binary_sha256": self.binary_sha256,
                "library_version": self.library["library_version"], "library_sha256": self.library["_sha256"],
                "args": args, "cache_key": key, "input_files_sha256": self.input_files_sha256,
                "contact_scenario": self.contact_scenario,
                "assumptions": ["PCE = MPP / 1000 W m^-2 (1-sun AM1.5G)",
                                f"device_setup from library for architecture {norm['architecture']} "
                                "(SimSS v5.36 defaults: T 295 K, ideal contacts S<0; p-i-n: anode left, sfb work functions, Cu back)"]}
        wd = self._prepare_dir(len(norm["layers"]))
        t0 = time.perf_counter()
        try:
            p = subprocess.run([str(self.binary)] + args, cwd=wd, capture_output=True, text=True,
                               errors="replace", timeout=self.timeout_s)
            dt = time.perf_counter() - t0
            parsed = parse_stdout(p.stdout)
            status, reason, metrics, warns = classify(parsed)
            if p.returncode not in (0, 95):
                warns.append(f"unexpected SimSS return code {p.returncode}")
                if status != "failed":
                    status, reason = "failed", f"SimSS return code {p.returncode}: {p.stderr.strip()[:200]}"
            vmax = float(dict(zip(args[0::2], args[1::2])).get("-Vmax", 1.4))
            if metrics.get("voc_V") is not None and metrics["voc_V"] >= vmax - 0.03:
                # Voc within ~1 voltage step of the sweep end: the J-V curve is extraction-blocked (S-shape) and may not
                # cross zero inside the sweep. The MPP of such a curve is set by where the barrier chokes the current,
                # not by a working diode (agy review 2026-09-28): FAIL, keep the numbers only as diagnostics.
                warns.append(f"Voc {metrics['voc_V']} V at the sweep edge (Vmax {vmax} V); diagnostic metrics kept in warnings")
                warns.append(f"diagnostic (NOT a result): pce {metrics.get('pce_pct')} voc {metrics.get('voc_V')} ff {metrics.get('ff')}")
                status, reason = "failed", f"Voc at sweep edge ({metrics['voc_V']} V >= Vmax - 0.03): S-shaped / blocked J-V"
                metrics.update({"pce_pct": None, "voc_V": None, "ff": None})
            if p.returncode == 95 and status == "complete":   # 95 = SimSS 'could not determine' code
                warns.append("return code 95 with complete metrics")
            rc = p.returncode
        except subprocess.TimeoutExpired:
            dt, rc = time.perf_counter() - t0, None
            parsed = {"n_converged": 0, "n_nonconverged": 0, "first_nonconv_V": None, "n_conv_above_vmpp": 0,
                      "n_conv_below_vmpp": 0}
            status, reason, warns = "failed", f"timeout after {self.timeout_s:g} s", []
            metrics = {k: None for k in ("pce_pct", "jsc_mA_cm2", "voc_V", "ff", "vmpp_V", "mpp_W_m2")}
        finally:
            shutil.rmtree(wd, ignore_errors=True)
        conv = {k: parsed.get(k) for k in ("n_converged", "n_nonconverged", "first_nonconv_V",
                                           "n_conv_above_vmpp", "n_conv_below_vmpp")}
        res = SimResult(RESULT_SCHEMA, status, reason, dh, norm, metrics, conv, rc, round(dt, 3), prov, warns)
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=self.cache_dir)
            with os.fdopen(fd, "w") as fh:          # atomic: write temp file, then rename over
                fh.write(res.to_json())
            os.replace(tmp, self.cache_dir / f"{key}.json")
        return res

    def run_many(self, designs: list[dict], workers: int = 8) -> list[SimResult]:
        """Order-preserving parallel batch. Invalid designs raise before any simulation starts."""
        for d in designs:
            validate(d, self.library)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(self.run, designs))
