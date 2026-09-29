"""Monte Carlo uncertainty sweeps over feed composition and operating conditions.

Every sample draws a feed (component masses, trace concentrations,
pre-treatment share), a pressure and an activity coefficient for the trace
metals, runs the full condensation ladder and records summary metrics. The
question each sweep answers: do the paper's claims survive realistic
variation of the inputs?

Parallel backends: 'process' (all local cores) or 'ray' (a cluster of
servers; `ray start --head` on one node, `ray start --address=...` on the
others). Equilibrium solves are CPU work; GPUs are used by chamber.py.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .feed import DEFAULT_MASSES, DEFAULT_TRACES_PPM, make_feed
from .ladder import run_ladder

PRECIOUS = ["Au", "Pd", "Pt", "Ag"]
TOXIC_VOLATILE = ["Hg", "Cd", "Zn", "Pb"]


@dataclass
class SweepConfig:
    samples: int = 200
    seed: int = 20260928
    mass_sigma: float = 0.30        # lognormal spread of component masses
    trace_sigma: float = 0.60       # lognormal spread of trace concentrations
    pretreat_range: tuple[float, float] = (0.0, 0.30)
    pressures_atm: tuple[float, ...] = (0.1, 1.0, 5.0)
    gamma_range: tuple[float, float] = (0.3, 3.0)   # log-uniform (vapor model only)
    dT: float = 50.0
    trace_model: str = "chemistry"
    # activity coefficients without data: ideal, uncertain by this factor
    unknown_pairs: tuple[tuple[str, str], ...] = (("Pt", "Fe"), ("Pt", "Cu"), ("Pd", "Cu"), ("Au", "Ni"),
                                                  ("Ag", "Ni"), ("Pd", "Ni"), ("Pt", "Ni"))
    unknown_factor: float = 3.0
    trace_data_sets: tuple[str, ...] = ("least_volatile", "central", "most_volatile")
    timeout_s: float = 600.0        # a feed taking longer is recorded as failed, not waited on


def draw(cfg: SweepConfig, i: int) -> dict:
    rng = np.random.default_rng([cfg.seed, i])
    masses = {k: v * rng.lognormal(0.0, cfg.mass_sigma) for k, v in DEFAULT_MASSES.items()}
    traces = {k: v * rng.lognormal(0.0, cfg.trace_sigma) for k, v in DEFAULT_TRACES_PPM.items()}
    return {
        "sample": i,
        "masses": masses,
        "traces": traces,
        "hg_ppm": 2.0 * rng.lognormal(0.0, cfg.trace_sigma),
        "pretreat": float(rng.uniform(*cfg.pretreat_range)),
        "P_atm": float(rng.choice(cfg.pressures_atm)),
        "gamma": float(np.exp(rng.uniform(*np.log(cfg.gamma_range)))),
        "dT": cfg.dT,
        "timeout_s": cfg.timeout_s,
        **_draw_chemistry(cfg, rng),
    }


def _draw_chemistry(cfg: SweepConfig, rng) -> dict:
    """Per-pair activity-coefficient factors, log-uniform within each pair's
    stated uncertainty (data/trace_gamma.json), and a chloride data set."""
    if cfg.trace_model != "chemistry":
        return {}
    from .trace_chem import henry_gamma
    pairs = {k: p["factor"] for k, p in henry_gamma().table.items()}
    pairs.update({k: cfg.unknown_factor for k in cfg.unknown_pairs})
    scale = {f"{a}|{b}": float(np.exp(rng.uniform(-np.log(f), np.log(f)))) for (a, b), f in sorted(pairs.items())}
    return {"gamma_scale": scale, "trace_data": str(rng.choice(cfg.trace_data_sets)),
            "trace_model": cfg.trace_model}


def evaluate(params: dict) -> dict:
    """Run one sample and return scalar metrics (picklable for any backend)."""
    feed = make_feed(params["masses"], params["pretreat"], traces_ppm=params["traces"],
                     hg_ppm=params["hg_ppm"])
    if params.get("trace_model", "vapor") == "chemistry":
        from .trace_chem import henry_gamma
        scale = {tuple(k.split("|")): v for k, v in params["gamma_scale"].items()}
        res = run_ladder(feed, P=params["P_atm"] * 101325.0, dT=params["dT"], trace_model="chemistry",
                         trace_data=params["trace_data"], trace_gamma=henry_gamma(scale))
    else:
        res = run_ladder(feed, P=params["P_atm"] * 101325.0, dT=params["dT"], gamma=params["gamma"],
                         trace_model="vapor")
    t50 = res.condensation_temperature()
    rec = res.recovery_table()
    grams = res.band_table()
    out = {k: params[k] for k in ("sample", "pretreat", "P_atm", "gamma")}
    if "gamma_scale" in params:
        out["trace_data"] = params["trace_data"]
        out.update({f"scale_{k.replace('|', '_in_')}": v for k, v in params["gamma_scale"].items()
                    if k.split("|")[0] in ("Au", "Pd", "Pt", "Ag")})
    out["dry_kg"] = feed.dry_kg
    d = res.duties
    out["steps"] = int(len(d))
    out["steps_certified"] = int(d["certified"].astype(bool).sum()) if "certified" in d else -1
    out["steps_cantera"] = int((d["solver"] == "cantera-vcs").sum()) if "solver" in d else -1
    for el, T in t50.items():
        out[f"T50_{el}"] = T
    # Where do precious metals go, and how concentrated is that band?
    for el in PRECIOUS:
        if el in rec.index:
            band = rec.loc[el].idxmax()
            out[f"band_{el}"] = band
            out[f"share_{el}"] = float(rec.loc[el].max())
            out[f"ppm_in_band_{el}"] = float(grams.loc[el, band] / grams[band].sum() * 1e6)
            for b_ in rec.columns:
                out[f"{el}_in_{b_}"] = float(rec.loc[el, b_])
    # Do toxic volatiles end up away from the precious metals? Check the main gold
    # band and every band that collects at least 10% of the gold.
    au_band = out.get("band_Au")
    gold_bands = [b_ for b_ in rec.columns if "Au" in rec.index and rec.loc["Au", b_] >= 0.10]
    for el in TOXIC_VOLATILE:
        if el in rec.index and au_band:
            out[f"{el}_in_Au_band"] = float(rec.loc[el].get(au_band, 0.0))
            out[f"{el}_in_gold_bands"] = float(sum(rec.loc[el].get(b_, 0.0) for b_ in gold_bands))
            out[f"{el}_left_in_gas"] = float(rec.loc[el].get("gas", 0.0))
    out["gold_bands"] = "".join(gold_bands)
    return out


def available_cpus() -> int:
    """CPUs this process may actually use: the container's cgroup CPU quota
    (v2, then v1) if set, else the affinity mask. os.cpu_count() reports the
    host's cores (e.g. 256 on a RunPod node whose pod gets ~31)."""
    n = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    for path, split in (("/sys/fs/cgroup/cpu.max", None),
                        ("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "/sys/fs/cgroup/cpu/cpu.cfs_period_us")):
        try:
            if split is None:
                quota, period = open(path).read().split()[:2]
            else:
                quota, period = open(path).read().strip(), open(split).read().strip()
            if quota not in ("max", "-1"):
                return max(1, min(n, int(quota) // int(period)))
        except (OSError, ValueError):
            continue
    return n


def _safe_evaluate(params: dict) -> dict:
    """evaluate() with a time limit; failures become rows, so one bad feed
    cannot stop or silently shrink the sweep (12_sweep_analysis reports them)."""
    import signal

    def _alarm(signum, frame):
        raise TimeoutError(f"feed took longer than {params['timeout_s']:.0f} s")

    use_alarm = params.get("timeout_s") and hasattr(signal, "SIGALRM")
    if use_alarm:
        old = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(int(params["timeout_s"]))
    try:
        return evaluate(params)
    except Exception as e:                   # noqa: BLE001 - recorded, not hidden
        return {"sample": params["sample"], "P_atm": params["P_atm"],
                "error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


def _iter_rows(tasks: list[dict], backend: str, workers: int | None):
    """Yield metric rows as samples finish (completion order, not sample order)."""
    if backend == "ray":
        import ray

        ray.init(address=os.environ.get("RAY_ADDRESS", "auto"), ignore_reinit_error=True)
        remote = ray.remote(num_cpus=1)(_safe_evaluate)
        pending = [remote.remote(t) for t in tasks]
        while pending:
            ready, pending = ray.wait(pending, num_returns=1)
            yield ray.get(ready[0])
    elif backend == "process":
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=workers or available_cpus()) as ex:
            for fut in as_completed([ex.submit(_safe_evaluate, t) for t in tasks]):
                yield fut.result()
    else:
        for t in tasks:
            yield _safe_evaluate(t)


def run(cfg: SweepConfig, backend: str = "process", workers: int | None = None,
        checkpoint: Path | None = None,
        progress: Callable[[int, int, int], None] | None = None) -> pd.DataFrame:
    """Run the sweep. With `checkpoint`, each finished row is appended (JSON lines)
    as it completes and samples already in the file are skipped, so a crashed
    run resumes where it stopped. `progress(done, total, resumed)` is called
    after every sample."""
    tasks = [draw(cfg, i) for i in range(cfg.samples)]
    rows = {}
    if checkpoint is not None and Path(checkpoint).exists():
        for line in Path(checkpoint).read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:   # torn last line from a crash
                continue
            rows[row["sample"]] = row
    resumed = len(rows)
    todo = [t for t in tasks if t["sample"] not in rows]
    sink = open(checkpoint, "a") if checkpoint is not None else None
    if sink and sink.tell() and not Path(checkpoint).read_text().endswith("\n"):
        sink.write("\n")                  # don't glue new rows onto a torn line
    try:
        for row in _iter_rows(todo, backend, workers):
            rows[row["sample"]] = row
            if sink:
                sink.write(json.dumps(row, default=float) + "\n")
                sink.flush()
                os.fsync(sink.fileno())
            if progress:
                progress(len(rows), cfg.samples, resumed)
    finally:
        if sink:
            sink.close()
    return pd.DataFrame([rows[i] for i in sorted(rows)])
