"""Generate the data tables of AllExplainedHere.tex from simulation/results.

Every number in these tables is read from the files the experiment scripts
wrote (or from the feed model), so the companion document cannot drift from
the code. build.sh runs this first and deletes the generated tables/ after.

    python make_tables.py        # writes tables/*.tex
"""
from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SIM = ROOT / "simulation"
RES = SIM / "results"
OUT = HERE / "tables"
sys.path.insert(0, str(SIM))
K = json.loads((RES / "key_numbers.json").read_text())


def f(x, d=3):
    """Number to LaTeX-safe text."""
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "--"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return f"{x:,}".replace(",", "{,}")
    if isinstance(x, float):
        if x == 0:
            return "0"
        a = abs(x)
        if a >= 1e4:
            return f"{x:,.0f}".replace(",", "{,}")
        if a >= 100:
            return f"{x:.0f}"
        if a >= 0.01:
            return f"{x:.{d}g}"
        m, e = f"{x:.2e}".split("e")
        return f"${m}\\times10^{{{int(e)}}}$"
    return tex(str(x))


def tex(s: str) -> str:
    if "$" in s or "\\" in s:          # already LaTeX (math or commands): leave as written
        return s
    return (s.replace("\\", "/").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")
            .replace("#", "\\#").replace(">=", "$\\ge$").replace("<=", "$\\le$").replace(">", "$>$")
            .replace("<", "$<$"))


def pct(x, d=1):
    return "--" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}"


def tabular(df: pd.DataFrame, spec: str | None = None, fmt=f, long=False, size="\\small") -> str:
    cols = list(df.columns)
    spec = spec or ("l" + "r" * (len(cols) - 1))
    head = " & ".join(f"\\textbf{{{tex(str(c))}}}" for c in cols) + " \\\\"
    rows = []
    for _, r in df.iterrows():
        rows.append(" & ".join(fmt(v) if not isinstance(v, str) else tex(v) for v in r.values) + " \\\\")
    if long:
        return (f"{{{size}\n\\begin{{longtable}}{{@{{}}{spec}@{{}}}}\n\\toprule\n{head}\n\\midrule\n\\endhead\n"
                + "\n".join(rows) + "\n\\bottomrule\n\\end{longtable}}\n")
    return (f"\\par\\smallskip{{{size}\\centering\n\\begin{{tabular}}{{@{{}}{spec}@{{}}}}\n\\toprule\n{head}\n\\midrule\n"
            + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\\par}\\smallskip\n")


def write(name, body, caption=None):
    OUT.mkdir(exist_ok=True)
    text = body if caption is None else f"\\begin{{center}}\n\\textbf{{{caption}}}\\\\[3pt]\n{body}\\end{{center}}\n"
    (OUT / f"{name}.tex").write_text(text)


def csv(name, **kw):
    return pd.read_csv(RES / name, **kw)


# ---------------------------------------------------------------- feed
from paramanu_sim import feed as F  # noqa: E402

rows = []
for comp, m in F.DEFAULT_MASSES.items():
    name = {"protein_N": "protein"}
    parts = ", ".join(f"{name.get(k, k)} {100 * v:.1f}%" if v >= 0.001 else f"{name.get(k, k)} {1e6 * v:.0f} ppm"
                      for k, v in sorted(F.COMPONENTS[comp].items(), key=lambda kv: -kv[1]))
    rows.append({"Component": comp, "kg per wet t": m, "Composition (mass fractions)": parts})
df = pd.DataFrame(rows)
write("feed_components", tabular(df, "l r >{\\raggedright\\arraybackslash}p{10cm}",
                                 fmt=lambda v: f(v), long=True, size="\\footnotesize"))
fd = F.make_feed()
from paramanu_sim.thermo import ATOMIC_MASS  # noqa: E402
em = {e: n for e, n in fd.element_moles.items() if n > 0}
tot = sum(em.values())
df = pd.DataFrame([{"Element": e, "mol": n, "kg": n * ATOMIC_MASS[e] / 1000, "mole share (%)": 100 * n / tot}
                   for e, n in sorted(em.items(), key=lambda kv: -kv[1])])
write("feed_elements", tabular(df, "lrrr", long=True, size="\\footnotesize"))
df = pd.DataFrame([{"Trace": k, "ppm of dry feed": v, "grams per wet tonne": fd.trace_grams.get(k, float("nan"))}
                   for k, v in F.DEFAULT_TRACES_PPM.items()] + [{"Trace": "Hg", "ppm of dry feed": F.DEFAULT_HG_PPM,
                                                                 "grams per wet tonne": float("nan")}])
write("feed_traces", tabular(df, "lrr"))
df = pd.DataFrame([{"Oxide": k, "wt% (renormalized)": v} for k, v in F.CRUST.items()])
write("feed_crust", tabular(df, "lr"))
df = pd.DataFrame([{"Metal": k, "mg per kg dry fines": v} for k, v in F.FINES_METALS_MG_KG.items()])
write("feed_fines_metals", tabular(df, "lr"))

# ---------------------------------------------------------------- validation
v = csv("validation_boiling_points.csv")
write("validation_bp", tabular(v.rename(columns={"model_K": "model (K)", "CRC_K": "CRC (K)",
                                                  "error_K": "error (K)", "error_pct": "error (%)"})))
g = csv("validation_gas_crosscheck.csv")
gg = g.groupby("T").agg(species=("species", "count"), max_rel_diff=("rel_diff", "max")).reset_index()
write("validation_gas", tabular(gg.rename(columns={"T": "T (K)", "species": "species compared",
                                                    "max_rel_diff": "max relative difference"})))

# ---------------------------------------------------------------- ladder
r = csv("ladder_band_recovery.csv", index_col=0)
r = (100 * r).round(1)
r.insert(0, "Element", r.index)
write("ladder_recovery", tabular(r.reset_index(drop=True), "l" + "r" * (len(r.columns) - 1),
                                 fmt=lambda x: "0" if x == 0 else f"{x:.1f}", long=True, size="\\footnotesize"))
t = csv("ladder_condensation_T.csv", index_col=0)
t.insert(0, "Element", t.index)
t = t.sort_values("T50", ascending=False)
write("ladder_T", tabular(t.reset_index(drop=True).rename(columns={"T10": "10% (K)", "T50": "50% (K)", "T90": "90% (K)"}),
                          "lrrr", long=True, size="\\footnotesize"))
m = K["ladder_band_mass_kg"]
mk = K["ladder_band_metal_kg"]
df = pd.DataFrame([{"Band": b, "total kg per wet t": m[b], "of which metal (kg)": mk.get(b, float("nan"))} for b in m])
write("ladder_mass", tabular(df, "lrr"))

rd = csv("reductant_metal_share.csv")
rd = rd.rename(columns={"element": "Metal / ratio", "0.0": "organics x0", "0.5": "x0.5", "1.0": "x1", "2.0": "x2"})
write("reductant", tabular(rd, "lrrrr", fmt=lambda x: f"{x:.2f}"))

# ---------------------------------------------------------------- energy
e = csv("energy_envelope.csv")
e = e[["pretreat", "P_atm", "dry_kg", "all_gas_T", "MWh_at_all_gas_T", "MWh_at_5000K", "gas_mol"]]
e.columns = ["pre-treat", "P (atm)", "dry kg", "all-gas T (K)", "MWh/t at all-gas T", "MWh/t at 5000 K", "gas mol"]
write("energy_envelope", tabular(e, "rrrrrrr"))
c = csv("energy_curve_1atm.csv")
c = c[c["T"].isin([300, 500, 1000, 1500, 2000, 2250, 2500, 2750, 3000, 3500, 4000, 5000])]
c.columns = ["T (K)", "MWh per wet t", "gas mol", "condensed mol"]
write("energy_curve", tabular(c, "rrrr"))

# ---------------------------------------------------------------- chamber and design
ch = csv("chamber_sizing.csv")
ch = ch[["batch_kg", "P_atm", "T_K", "volume_m3", "diameter_m", "emissivity", "radiation_MW", "batch_energy_MWh"]]
ch.columns = ["batch kg", "P (atm)", "T (K)", "volume m$^3$", "diameter m", "emissivity", "radiation MW", "batch MWh"]
write("chamber_sizing", tabular(ch, "rrrrrrrr", size="\\footnotesize"))
fl = csv("design_flow_loss.csv")
sel = fl[(fl.P_atm == 1.0) & (fl.residence_s.isin([0.001, 0.003, 0.01, 0.025, 0.05, 0.1, 0.3, 1.0]))]
pv = sel.pivot_table(index="residence_s", columns="t_per_day", values="loss_fraction").reset_index()
pv.columns = ["residence (s)"] + [f"{int(c):,} t/day".replace(",", "{,}") for c in pv.columns[1:]]
write("flow_loss", tabular(pv, "r" * len(pv.columns), fmt=lambda x: pct(x) + "\\%" if x < 1 else f"{x:g}"))
bt = csv("design_batch_time_constant.csv")
bt = bt[(bt.P_atm == 1.0) & (bt.T_wall == 600.0)][["batch_kg", "tau_s"]]
bt.columns = ["batch (kg)", "time constant (s)"]
write("batch_tau", tabular(bt, "rr"))
cd = csv("design_condenser_duty.csv")
cd.columns = ["band", "MWh per t", "MW at 1,000 t/day"]
write("condenser_duty", tabular(cd, "lrr"))
df = pd.DataFrame([{"T (K)": T, "ionized fraction": K.get(f"saha_ionization_{T}K_1atm")} for T in (3000, 5000, 8000, 10000)])
write("saha", tabular(df, "rr"))

# ---------------------------------------------------------------- theory
o = csv("theory_condensation_onset.csv")
o.columns = ["element", "gas mole fraction $y$", "$T_b$ (K)", "$\\Delta H_{vap}$ (kJ/mol)", "closed form (K)", "exact (K)",
             "simulated (K)"]
write("theory_onset", tabular(o, "lrrrrrr", size="\\footnotesize"))
rv = csv("theory_relative_volatility.csv")
rv.columns = ["light", "heavy", "T (K)", "$\\alpha$", "$N_{min}$ 99\\%", "$N_{min}$ 99.9\\%", "light left, 1 stage"]
write("theory_volatility", tabular(rv, "llrrrrr", size="\\footnotesize"))

# ---------------------------------------------------------------- breakdown
bm = csv("breakdown_residual_molecules.csv")
bm["species"] = bm.species.str.split(",").str[0]
pv = bm.pivot_table(index="species", columns="T", values="mole_fraction").reset_index()
pv.columns = ["molecule"] + [f"{int(c)} K" for c in pv.columns[1:]]
write("breakdown_molecules", tabular(pv, "l" + "r" * (len(pv.columns) - 1), size="\\footnotesize"))
bp = csv("breakdown_particle_times.csv")
pv = bp.pivot_table(index="d_um", columns="T_gas", values="t_ms").reset_index()
pv.columns = ["grain (µm)".replace("µ", "\\textmu ")] + [f"gas {int(c)} K (ms)" for c in pv.columns[1:]]
write("breakdown_particles", tabular(pv, "r" * len(pv.columns)))
bs = csv("breakdown_start_independence.csv")
pv = bs.pivot_table(index="T", columns="start", values="max_rel_diff_major").reset_index()
pv.columns = ["T (K)"] + [str(c) for c in pv.columns[1:]]
write("breakdown_starts", tabular(pv, "r" * len(pv.columns)))

# ---------------------------------------------------------------- robustness family
cv = csv("convergence.csv")
cv.columns = ["step (K)", "Au in B", "Fe in B", "Zn in E", "Hg gas", "T50 Fe", "T50 Cu", "T50 Zn"]
write("convergence", tabular(cv, "rrrrrrrr", size="\\footnotesize"))
s = csv("sensitivity.csv")
s.columns = ["case", "all-gas T (K)", "MWh per t", "Au main-band share", "Hg left in gas"]
write("sensitivity", tabular(s, "lrrrr"))
a = csv("alloy_T50.csv")
a.columns = ["element", "pure phases (K)", "ideal alloy (K)"]
a["change (K)"] = a["ideal alloy (K)"] - a["pure phases (K)"]
write("alloy_T50", tabular(a, "lrrr", long=True, size="\\footnotesize"))
gc = csv("gold_copper_ladder.csv")
gc = gc[gc.element == "Au"] if "element" in gc else gc
cols = ["scenario"] + [c for c in gc.columns if c.startswith("band_")] + ["main_band"]
gc = gc[cols].copy()
gc.columns = ["scenario"] + [c.replace("band_", "") for c in cols[1:-1]] + ["main"]
num_cols = gc.columns[1:-1]
gc[num_cols] = gc[num_cols] * 100
write("gold_scenarios", tabular(gc, "l" + "r" * (len(gc.columns) - 2) + "l",
                                fmt=lambda x: "0" if abs(x) < 0.05 else f"{x:.1f}", size="\\footnotesize"))

# ---------------------------------------------------------------- benchmarks
bv = csv("benchmark_vapor_pressure.csv")
bv.columns = ["T (\\textdegree C)", "Pb lit. (Pa)", "Sn lit. (Pa)", "Pb model", "Sn model", "Pb ratio", "Sn ratio"]
write("bench_vp", tabular(bv, "rrrrrrr", size="\\footnotesize"))
be = csv("benchmark_eaf_dust.csv")
be = be[be.T_C == 1300][["C/O", "gas", "Zn_removal_pct", "Fe_metallization_pct", "measured_Zn_removal_pct_1300C",
                          "measured_Fe_metallization_1300C"]]
be.columns = ["C/O", "gas", "Zn removal model (%)", "Fe metal model (%)", "Zn removal measured (%)", "Fe metal measured (%)"]
write("bench_eaf", tabular(be, "rlrrrr", size="\\footnotesize"))
bg = csv("gold_copper_benchmark.csv")
bg = bg[["element", "gamma_in_Fe", "gamma_in_Cu", "L_FeCu_predicted", "L_FeCu_measured_FeCuP", "L_FeCu_measured_FeCuPC"]]
bg.columns = ["element", "$\\gamma$ in Fe", "$\\gamma$ in Cu", "L predicted", "L measured (Fe-Cu-P)", "L measured (Fe-Cu-P-C)"]
write("bench_gold", tabular(bg, "lrrrrr", size="\\footnotesize"))

# ---------------------------------------------------------------- catalysts
cs = csv("catalyst_survival.csv")
cs.columns = ["catalyst", "size", "p$_{sat}$ (Pa)", "flux (kg/m$^2$/s)", "lifetime (s)"]
write("cat_survival", tabular(cs, "llrrr"))
cdh = csv("catalyst_damkohler_hot.csv")
cdh.columns = ["T (K)", "CF$_4$ lifetime (s)", "Da (25 ms)"]
write("cat_damkohler", tabular(cdh, "rrr"))
cc = csv("catalyst_carbothermic_sio.csv")
cc.columns = ["p$_{SiO}$ (atm)", "T with carbon (K)", "T silica alone (K)"]
cc["lowered by (K)"] = cc["T silica alone (K)"] - cc["T with carbon (K)"]
write("cat_carbo", tabular(cc, "rrrr"))

# ---------------------------------------------------------------- landfill
lf = csv("landfill_inventory.csv")
lf = lf[["element", "stream", "form", "captured", "refining_yield", "theoretical_lb", "practical_lb"]]
lf.columns = ["element", "band(s)", "form", "captured", "refining yield", "theoretical lb", "practical lb"]
write("landfill", tabular(lf, "lllrrrr", long=True, size="\\footnotesize"))

# ---------------------------------------------------------------- sweep
LABEL = {"feeds": "feeds", "Au_band_B": "gold mainly in B (share of feeds)", "Au_band_A": "gold mainly in A",
         "Au_band_C": "gold mainly in C", "Au_band_D1": "gold mainly in D1", "Au_band_D2": "gold mainly in D2",
         "Au_in_B_median": "gold in B, median", "Au_in_C_median": "gold in C, median",
         "Au_in_BC_median": "gold in B+C, median", "Au_in_BC_p05": "gold in B+C, 5th percentile",
         "T50_Fe_median": "T50 of Fe, median (K)", "T50_Au_median": "T50 of Au, median (K)",
         "Au_same_band_as_Fe": "gold's T50 in iron's band", "share_Au_median": "gold in its main band, median",
         "Cd_in_Au_band_max": "cadmium in gold's main band, max", "Hg_gas_median": "mercury gaseous at 300 K, median",
         "Hg_gas_p05": "mercury gaseous, 5th percentile", "Hg_gas_p95": "mercury gaseous, 95th percentile",
         "T50_Cu": "T50 of Cu (K)", "T50_Pb": "T50 of Pb (K)", "T50_Zn": "T50 of Zn (K)", "T50_Fe": "T50 of Fe (K)",
         "T50_Au": "T50 of Au (K)", "Hg_left_in_gas": "mercury gaseous at 300 K", "share_Au": "gold in its main band",
         "dry_kg": "dry feed (kg)"}
bp_ = csv("sweep_5000_by_pressure.csv").set_index("P_atm").T.reset_index()
bp_["index"] = bp_["index"].map(lambda c: LABEL.get(c, c))
bp_.columns = ["quantity"] + [f"{c:g} atm" for c in bp_.columns[1:]]
write("sweep_by_pressure", tabular(bp_, "lrrr", size="\\footnotesize"))
cl = K["sweep_5000_claims"]
rows = []
for el in ("Zn", "Hg", "Pb", "Cd"):
    x = cl[f"{el}_in_gold_bands"]
    rows.append({"metal": el, "feeds containing it": x["feeds_containing"], "feeds with any in a gold band": x["feeds_with_any"],
                 "largest share": x["max"], "95% bound on rate": x["rate_bound_95"]})
write("sweep_claims", tabular(pd.DataFrame(rows), "lrrrr"))
rows = [{"band": b, "median (%)": 100 * cl[f"Au_share_in_{b}"]["median"], "5th pct (%)": 100 * cl[f"Au_share_in_{b}"]["p05"],
         "95th pct (%)": 100 * cl[f"Au_share_in_{b}"]["p95"]} for b in ("A", "B", "C", "D1", "D2") if f"Au_share_in_{b}" in cl]
write("sweep_gold", tabular(pd.DataFrame(rows), "lrrr", fmt=lambda x: f"{x:.1f}"))
sw = csv("sweep_5000.csv")
q = sw[["T50_Fe", "T50_Au", "T50_Cu", "T50_Pb", "T50_Zn", "Hg_left_in_gas", "share_Au", "dry_kg"]].describe(
    percentiles=[.05, .5, .95]).T[["5%", "50%", "95%"]].reset_index()
q.columns = ["quantity", "5th percentile", "median", "95th percentile"]
q["quantity"] = q["quantity"].map(lambda c: LABEL.get(c, c))
write("sweep_quantiles", tabular(q, "lrrr"))

# ---------------------------------------------------------------- verification
vs = csv("verification_independent_solver.csv")
vs = vs[["case", "T", "cantera_solver", "same_phase_set", "n_condensed", "max_rel_diff_condensed", "max_rel_diff_gas_major",
         "paramanu_certified"]]
vs.columns = ["case", "T (K)", "Cantera", "same phases", "phases", "max rel. diff. condensed", "max rel. diff. gas", "certified"]
vs["same phases"] = vs["same phases"].map({True: "yes", False: "no"}).fillna("--")
vs["certified"] = vs["certified"].map({True: "yes", False: "no"}).fillna("--")
write("verif_solver", tabular(vs, "lrlrrrrl", long=True, size="\\footnotesize"))
vd = csv("verification_independent_data.csv")
vd = vd[["element", "T50_cantera_nasa7", "T50_cea_nasa9", "diff_K", "main_band_nasa7", "main_band_nasa9"]]
vd.columns = ["element", "T50 NASA-7 (K)", "T50 NASA-9 (K)", "difference (K)", "band NASA-7", "band NASA-9"]
write("verif_data", tabular(vd, "lrrrll", long=True, size="\\footnotesize"))
fa = csv("falsification.csv")
rows = []
for claim, grp in fa.groupby("claim", sort=False):
    sh = grp.share_in_gold_bands.fillna(0)
    rows.append({"claim": claim, "tried": len(grp), "not computed": int((grp.error.fillna("") != "").sum()),
                 "worst share": sh.max(), "feeds > 0": int((sh > 0).sum()),
                 "min. gap (K)": grp.gap_K.min(), "P tried (atm)": f"{grp.P_atm.min():.2f}--{grp.P_atm.max():.2f}"})
write("falsification", tabular(pd.DataFrame(rows), "lrrrrrr", size="\\footnotesize"))
gs = csv("global_sensitivity.csv")
gs = gs[gs.significant].sort_values(["subset", "output", "S1"], ascending=[True, True, False])
top = gs.groupby(["subset", "output"]).head(4)[["subset", "output", "input", "S1"]].copy()
top["input"] = (top.input.str.replace("_in_", " in ").str.replace("gamma_", "activity coeff. ")
                .str.replace("mass_", "mass of ").str.replace("trace_", "trace ").str.replace("hg_ppm", "mercury content")
                .str.replace("pretreat", "pre-treatment").str.replace("chloride_data", "chloride data set"))
top.columns = ["feeds", "output", "input", "first-order index"]
write("sobol", tabular(top, "llll", fmt=lambda x: f"{x:.3f}", long=True, size="\\footnotesize"))

# ---------------------------------------------------------------- scripts and tests catalogue
rows = []
for p in sorted((SIM / "scripts").glob("[0-9][0-9]_*.py")):
    doc = ast.get_docstring(ast.parse(p.read_text())) or ""
    first = re.sub(r"^Experiment \d+ - ", "", doc.strip().splitlines()[0]) if doc else ""
    rows.append({"script": p.name, "what it answers": first})
write("scripts", tabular(pd.DataFrame(rows), "l>{\\raggedright\\arraybackslash}p{10.5cm}", long=True, size="\\footnotesize"))
rows = []
for p in sorted((SIM / "tests").glob("test_*.py")):
    tree = ast.parse(p.read_text())
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
            d = (ast.get_docstring(n) or "").strip().split(". ")[0].replace("\n", " ")
            d = d or n.name.replace("test_", "").replace("_", " ").capitalize()
            if any(isinstance(dec, ast.Call) and "parametrize" in ast.unparse(dec) for dec in n.decorator_list):
                d += " (run for several cases)"
            rows.append({"file": p.name, "test": n.name.replace("test_", ""), "checks": d})
write("tests", tabular(pd.DataFrame(rows), "l>{\\raggedright\\arraybackslash}p{5.2cm}>{\\raggedright\\arraybackslash}p{6.6cm}",
                       long=True, size="\\scriptsize"))
print(f"wrote {len(list(OUT.glob('*.tex')))} tables to {OUT}")
