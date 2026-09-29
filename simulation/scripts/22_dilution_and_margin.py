"""Experiment 22 - Two checks a referee will ask for.

(a) Dilution by torch gas. The plasma torches and a protective gas curtain add
    gas (argon, or the process's own recycled gas) to the heap. By Result 3 this
    lowers every partial pressure yP and so every condensation temperature. The
    default ladder is rerun with argon equal to 0.5 and 1.0 times the heap's own
    gas moles at the all-gas state.
(b) Margin of the Band D split. For the lead claim, the adversarial search
    (20_falsification.py) records the feed that brought lead closest to gold (the
    smallest gap between their half-condensation temperatures). That feed is
    rerun in 12.5 K steps, and we record the temperature by which 99.9% of its
    gold has condensed and the temperature at which the first 0.1% of its lead
    condenses. The D1/D2 boundary at 1,300 K must lie between them.

    python 22_dilution_and_margin.py
"""
import _common  # noqa: F401
import json
import math

import cantera as ct
import pandas as pd

from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.energy import all_gas_temperature
from paramanu_sim.feed import DEFAULT_MASSES, DEFAULT_TRACES_PPM, make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.sweep import SweepConfig
from paramanu_sim.trace_chem import henry_gamma

# ---------------------------------------------------------------- (a) dilution
base = make_feed()
T_all = all_gas_temperature(base, ct.one_atm)
n_gas = sum(equilibrate(base.element_moles, T_all, ct.one_atm).gas.values())
rows = []
for f in (0.0, 0.5, 1.0):
    lad = run_ladder(make_feed(argon_mol=f * n_gas), dT=25.0)
    r, t = lad.recovery_table(), lad.condensation_temperature()
    gold_bands = [b for b in r.columns if r.loc["Au", b] >= 0.10]
    rows.append({"argon_per_heap_gas": f, "Au_in_B": r.loc["Au", "B"], "Au_in_C": r.loc["Au", "C"],
                 "gold_bands": "".join(gold_bands),
                 "Pb_in_gold_bands": float(sum(r.loc["Pb", b] for b in gold_bands)),
                 "Zn_in_gold_bands": float(sum(r.loc["Zn", b] for b in gold_bands)),
                 **{f"T50_{e}": float(t.get(e, float("nan"))) for e in ("Fe", "Au", "Cu", "Pb", "Zn")},
                 "Hg_left_in_gas": float(r.loc["Hg", "gas"])})
dil = pd.DataFrame(rows)
dil.to_csv(RESULTS / "dilution_argon.csv", index=False)
record("dilution_argon", dil.round(4).to_dict(orient="records"))
print(dil.round(3).to_string(index=False))

# ---------------------------------------------------------------- (b) margin
cfg = SweepConfig()
fa = pd.read_csv(RESULTS / "falsification.csv")
lead = fa[(fa.claim == "lead") & (fa.error.fillna("") == "")]
worst = lead.loc[lead.gap_K.idxmin()]
x = json.loads(worst.x)
# decode the search vector exactly as 20_falsification.py does
from paramanu_sim.sweep import _draw_chemistry  # noqa: E402
import numpy as np  # noqa: E402
gamma_keys = sorted(_draw_chemistry(cfg, np.random.default_rng(0))["gamma_scale"])
MASS, TRACE = sorted(DEFAULT_MASSES), sorted(DEFAULT_TRACES_PPM)
i = 0
masses = {k: DEFAULT_MASSES[k] * math.exp(x[i + j]) for j, k in enumerate(MASS)}
i += len(MASS)
traces = {k: DEFAULT_TRACES_PPM[k] * math.exp(x[i + j]) for j, k in enumerate(TRACE)}
i += len(TRACE)
hg, pre, P = 2.0 * math.exp(x[i]), float(x[i + 1]), math.exp(x[i + 2])
i += 3
scale = {tuple(k.split("|")): math.exp(x[i + j]) for j, k in enumerate(gamma_keys)}
data = list(cfg.trace_data_sets)[int(x[-1])]
feed = make_feed(masses, pre, traces_ppm=traces, hg_ppm=hg)
lad = run_ladder(feed, P=P * ct.one_atm, dT=12.5, trace_data=data, trace_gamma=henry_gamma(scale))
st = lad.steps


def temp_at(el, frac):
    s = st[st.element == el].sort_values("T", ascending=False)
    c = s.moles.cumsum() / s.moles.sum()
    return float(s["T"][c >= frac].iloc[0])


margin = {"feed_P_atm": P, "feed_pretreat": pre, "gap_T50_K_in_search": float(worst.gap_K),
          "gold_999_condensed_by_K": temp_at("Au", 0.999), "lead_first_001_condensed_at_K": temp_at("Pb", 0.001),
          "boundary_K": 1300.0}
margin["gap_K"] = margin["gold_999_condensed_by_K"] - margin["lead_first_001_condensed_at_K"]
record("band_split_margin", margin)
print(json.dumps(margin, indent=1))
