"""Experiment 9 - Numerical convergence: results do not depend on the step size."""
import _common  # noqa: F401
import pandas as pd

from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record

feed = make_feed()
rows = []
for dT in (100.0, 50.0, 25.0, 12.5):
    r = run_ladder(feed, T_start=3000.0, dT=dT)
    rec = r.recovery_table()
    t50 = r.condensation_temperature()
    rows.append({"dT_K": dT, "Au_in_B": rec.loc["Au"].get("B", 0), "Fe_in_B": rec.loc["Fe"].get("B", 0),
                 "Zn_in_E": rec.loc["Zn"].get("E", 0), "Hg_gas": rec.loc["Hg"].get("gas", 0),
                 "T50_Fe": t50["Fe"], "T50_Cu": t50["Cu"], "T50_Zn": t50["Zn"]})
df = pd.DataFrame(rows)
df.to_csv(RESULTS / "convergence.csv", index=False)
ref = df.iloc[-1]
last = df.iloc[-2]
change = {c: float(abs(last[c] - ref[c])) for c in df.columns if c != "dT_K"}
record("convergence_change_25K_to_12p5K", change)
print(df.round(4).to_string(index=False))
