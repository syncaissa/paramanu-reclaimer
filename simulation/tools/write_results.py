"""Write Results.txt: every published PARAMANU result in one plain-text file.

Reads only what the experiment scripts wrote to simulation/results/
(key_numbers.json and the CSV tables), so it is regenerated, never edited by
hand. Rerun it after any rerun of the experiments:

    cd simulation && python tools/write_results.py          # writes ../Results.txt
    python tools/write_results.py --fingerprint             # print the code fingerprint only

Each section names the script that produces it and the date of its source
file. A section whose source is missing says so instead of showing old numbers.
The code fingerprint (SHA-256 over every .py file of paramanu_sim/, scripts/
and tools/, plus requirements.txt and the data files) identifies exactly which
code produced the results; recompute it on your copy to check you have the same.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

SIM = Path(__file__).resolve().parents[1]
RES = SIM / "results"
OUT = SIM.parent / "Results.txt"
W = 78

# Every correction made to the code or the analysis after a result had been
# published internally, newest last. Add an entry whenever a fix changes results.
CORRECTIONS = [
    ("2026-09-28", "Sweep analysis: rule-of-three denominator",
     "The failure-rate bound divided by all 5,000 feeds, but only 971 contained zinc and lead "
     "(soil had none). Fixed the denominator (only feeds that contain the metal count) and gave the "
     "soil fines measured heavy metals (Vollprecht et al. 2020), so every feed now contains them."),
    ("2026-09-28", "Trace data: two faulty Burcat records rejected",
     "PtH (placeholder heat of formation) and SbF (unit error) failed the check of each record "
     "against its own stated heat of formation; excluded, with a test that keeps them out."),
    ("2026-09-29", "Solver: unconverged ladder steps",
     "PARAMANU's solver did not converge at 43 of 229 ladder steps below 1,850 K because "
     "parts-per-billion remnants were solved with the major elements. Elements below 1 ppm of the "
     "gas are now placed by the dilute-limit solver (Result 3) at the potentials of the majors."),
    ("2026-09-29", "Solver backup: Cantera's false convergence",
     "Cantera's VCS solver, added as a backup, reported convergence at 0.1 atm for states that are "
     "not the equilibrium (graphite with steam and no CO; zinc sulfate), putting zinc/lead/mercury "
     "in Bands C and D in 183 of 5,000 feeds. Every state must now pass the Result 2 certificate "
     "(equilibrium.certify); the affected sweep was discarded and rerun."),
    ("2026-09-29", "Solver: missing graphite",
     "The certificate found rare carbon-rich states at 0.1 atm, 1,400-1,450 K, where the solver "
     "left out graphite (supersaturated x1.4). The NASA CEA phase-set loop (gibbs.refine) now adds "
     "it. Before: 569,696 of 570,000 sweep states certified; after: all. Claims unchanged."),
    ("2026-09-29", "Design: Band D split at 1,300 K (found by the adversarial search)",
     "The falsification search (20_falsification.py) found organic-rich feeds at 1-1.4 atm where "
     "10-40% of the gold condenses at 1,300-1,600 K, inside Band D (1,000-1,600 K) with lead: up to "
     "49% of the lead was in a band holding >= 10% of the gold. Gold and lead never condense at the "
     "same temperature (checked on 17 feeds), so Band D is now D1 (1,300-1,600 K) and D2 "
     "(1,000-1,300 K). The sweep and the search were rerun on the revised design: no lead in any "
     "gold band in 5,000 sweep feeds or in 1,664 adversarial feeds; zinc, mercury 0%, cadmium <= 0.025%."),
    ("2026-09-29", "Hot-zone design: consistent basis (pre-publication review)",
     "08_reactor_design.py divided energy and gas by the 961 kg entering the reactor but multiplied by 1,000 "
     "t/day of excavated material. Now per excavated tonne throughout: 9.8 MJ/kg and 35.1 mol/kg (drying "
     "excluded), 96 m3/s of hot gas (was 100), torch power 113 MW without losses, 119/126 MW at 5%/10% "
     "radiation loss (was 124/130); residence limits (25 and 10 ms) and the 4.2 s batch time constant unchanged."),
]


def fingerprint() -> str:
    h = hashlib.sha256()
    files = sorted([*(SIM / "paramanu_sim").rglob("*.py"), *(SIM / "paramanu_sim" / "data").glob("*"),
                    *(SIM / "scripts").glob("*.py"), *(SIM / "tools").glob("*.py"), SIM / "requirements.txt"])
    for f in files:
        if f.is_file() and "__pycache__" not in f.parts:
            h.update(str(f.relative_to(SIM)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


K = json.loads((RES / "key_numbers.json").read_text()) if (RES / "key_numbers.json").exists() else {}


def k(name, default=None):
    return K.get(name, default)


def num(x, digits=3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return f"{x:,}"
    if isinstance(x, float):
        if x == 0:
            return "0"
        a = abs(x)
        if a >= 1000:
            return f"{x:,.0f}"
        if a >= 0.01:
            return f"{x:.{digits}g}"
        return f"{x:.2e}"
    return str(x)


def pct(x, digits=1) -> str:
    return "-" if x is None else f"{100 * x:.{digits}f}%"


def stamp(*files: str) -> str:
    out = []
    for f in files:
        p = RES / f
        out.append(f"{f} ({dt.datetime.utcfromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M} UTC)"
                   if p.exists() else f"{f} (MISSING)")
    return "Source: " + "; ".join(out)


def table(df: pd.DataFrame, floatfmt=num) -> str:
    df = df.copy()
    for c in df.columns:
        df[c] = [floatfmt(v) if isinstance(v, float) else
                 ", ".join(num(float(x)) for x in v) if isinstance(v, list) else
                 ", ".join(num(float(x)) for x in json.loads(v)) if isinstance(v, str) and v.startswith("[") else
                 str(v) for v in df[c]]
    return df.to_string(index=False)


def csv(name):
    p = RES / name
    return pd.read_csv(p) if p.exists() else None


SECTIONS = []


def section(title, script):
    def deco(fn):
        SECTIONS.append((title, script, fn))
        return fn
    return deco


def missing(script):
    return f"Not yet computed. Run: cd simulation/scripts && python {script}"


@section("Validation against known facts", "01_validate.py")
def _validation():
    if k("validation_bp_median_abs_error_pct") is None:
        return missing("01_validate.py")
    s = [stamp("validation_boiling_points.csv", "validation_gas_crosscheck.csv"), "",
         f"Normal boiling points of pure elements: median error {k('validation_bp_median_abs_error_pct')}%, "
         f"maximum {k('validation_bp_max_abs_error_pct')}%.",
         f"Gas mixtures (C,H,O,N,Si,Fe,Cl), 1,500-4,000 K, against Cantera's solver: max relative "
         f"difference {num(k('validation_gas_max_rel_diff'))}.", ""]
    bp = csv("validation_boiling_points.csv")
    if bp is not None:
        s.append(table(bp))
    return "\n".join(s)


@section("The condensation ladder, default feed, 1 atm", "02_ladder.py")
def _ladder():
    rec = csv("ladder_band_recovery.csv")
    if rec is None:
        return missing("02_ladder.py")
    s = [stamp("ladder_band_recovery.csv", "ladder_condensation_T.csv"), "",
         "Bands (K): A >= 2600, B 2000-2600, C 1600-2000, D1 1300-1600, D2 1000-1300, E 400-1000,",
         "cold < 400; 'gas' = still gaseous at 300 K. Share of each element collected in each band (%):", ""]
    rec = rec.set_index(rec.columns[0])
    rec.index.name = "element"
    s.append((rec * 100).round(1).to_string())
    t50 = k("ladder_T50_K", {})
    s += ["", "Half-condensation temperature T50 (K; '-' = never 50% condensed):",
          "  " + ", ".join(f"{e} {num(v)}" for e, v in sorted(t50.items(), key=lambda x: -(x[1] or 0)))]
    s += ["", "Mass collected per band (kg per wet tonne): " +
          ", ".join(f"{b} {v:.1f}" for b, v in k("ladder_band_mass_kg", {}).items()),
          f"Gold: {pct(k('ladder_Au_share_in_band'))} in its main band ({k('ladder_Au_band')}), "
          f"{num(k('ladder_Au_ppm_in_band_metal'))} ppm in that band's metal "
          f"({num(k('ladder_Au_enrichment_in_metal'))}x the feed's {k('ladder_Au_feed_ppm')} ppm).",
          f"Mercury still gaseous at 300 K: {pct(k('ladder_Hg_left_in_gas'))} (a mercury trap is required)."]
    return "\n".join(s)


@section("The waste as its own reducing agent", "03_reductant.py")
def _reductant():
    if k("reductant_ratio_default") is None:
        return missing("03_reductant.py")
    return "\n".join([stamp("reductant_metal_share.csv"), "",
                      f"Reductant ratio of the default feed: {num(k('reductant_ratio_default'))} "
                      "(> 1: more carbon and hydrogen than needed to reduce the metal oxides).",
                      "Share of iron condensed as metal, by reductant ratio: " +
                      ", ".join(f"{r}: {pct(v, 0)}" for r, v in k("reductant_Fe_metal_share", {}).items())])


@section("Energy", "04_energy.py")
def _energy():
    if k("energy_MWh_all_gas_1atm") is None:
        return missing("04_energy.py")
    s = [stamp("energy_envelope.csv"), "",
         f"All gas at {num(k('energy_all_gas_T_1atm'))} K (1 atm): thermodynamic minimum "
         f"{num(k('energy_MWh_all_gas_1atm'))} MWh per wet tonne; {num(k('energy_MWh_5000K_1atm'))} MWh at 5,000 K.",
         f"Torch power for 1,000 t/day at the minimum: {num(k('energy_MW_per_1000tpd'))} MW.",
         f"Minimum work of separation (Result 6): {num(k('theory_min_separation_work_MWh'))} MWh/t, "
         f"{pct(k('theory_min_work_share_of_vaporization'))} of the vaporization energy.", ""]
    et = k("energy_table")
    if et:
        s.append(table(pd.DataFrame(et)))
    return "\n".join(s)


@section("Chamber and reactor design (why the hot zone must be brief)", "05_chamber.py, 08_reactor_design.py")
def _chamber():
    if k("chamber_1t_1atm_volume_m3") is None:
        return missing("05_chamber.py")
    s = [stamp("chamber_sizing.csv", "design_flow_loss.csv"), "",
         f"1 t as gas at 1 atm: {num(k('chamber_1t_1atm_volume_m3'))} m3; wall radiation "
         f"{num(k('chamber_1t_1atm_radiation_MW'))} MW (a batch cannot be held hot).",
         "Maximum hot-zone residence for 10% / 5% radiation loss:"]
    for tpd in (10, 100, 1000):
        a, b = k(f"design_flow_max_residence_s_{tpd}tpd_loss10pct"), k(f"design_flow_max_residence_s_{tpd}tpd_loss5pct")
        s.append(f"  {tpd:>5} t/day: {num(a * 1000 if a else None)} ms / {num(b * 1000 if b else None)} ms")
    s.append("Condenser duty per band (MWh per tonne): " +
             ", ".join(f"{b} {v:.2f}" for b, v in k("design_condenser_duty_MWh_per_t", {}).items()))
    s.append("Ionization at 1 atm (Saha): " + ", ".join(
        f"{T} K {num(k(f'saha_ionization_{T}K_1atm'))}" for T in (3000, 5000, 8000, 10000)))
    return "\n".join(s)


@section("Closed-form theory checked against the simulation", "07_theory_checks.py")
def _theory():
    if k("theory_onset_max_abs_diff_K") is None:
        return missing("07_theory_checks.py")
    s = [stamp("theory_condensation_onset.csv", "theory_relative_volatility.csv"), "",
         f"Result 3 (closed-form condensation onset) against the full solver: max difference "
         f"{num(k('theory_onset_max_abs_diff_K'))} K.", ""]
    v = csv("theory_relative_volatility.csv")
    if v is not None:
        s.append(table(v))
    return "\n".join(s)


@section("Numerical convergence and one-at-a-time sensitivity", "09_convergence.py, 10_sensitivity.py")
def _conv():
    c = k("convergence_change_25K_to_12p5K")
    if c is None:
        return missing("09_convergence.py")
    s = [stamp("convergence.csv", "sensitivity.csv"), "",
         "Change when the ladder step is halved from 25 K to 12.5 K: " +
         ", ".join(f"{n} {num(v)}" for n, v in c.items()), ""]
    sens = csv("sensitivity.csv")
    if sens is not None:
        s.append(table(sens))
    return "\n".join(s)


@section("Alloying (ideal liquid-metal solution)", "11_alloy_model.py")
def _alloy():
    t = csv("alloy_T50.csv")
    if t is None:
        return missing("11_alloy_model.py")
    t = t.rename(columns={t.columns[0]: "element"})
    return "\n".join([stamp("alloy_T50.csv", "alloy_recovery.csv"), "",
                      "Half-condensation temperature (K) with pure condensed phases and with an ideal alloy:", table(t)])


@section("How complex waste comes apart", "13_breakdown.py")
def _breakdown():
    b = k("breakdown_fraction_2890K")
    if b is None:
        return missing("13_breakdown.py")
    return "\n".join([
        stamp("breakdown_residual_molecules.csv", "breakdown_particle_times.csv"), "",
        f"Three different starting mixtures with the same atoms reach the same state (max relative "
        f"difference {num(k('breakdown_max_rel_diff_between_starts'))}): Result 7.",
        "Equilibrium mole fraction of each starting molecule at 2,890 K:",
        "  " + ", ".join(f"{m} {num(v)}" for m, v in b.items()),
        f"Largest molecule of 6+ atoms: {num(k('breakdown_largest_6atom_fraction_2890K'))}.",
        "Largest silica grain that vaporizes within 10 / 25 ms (um): " + "; ".join(
            f"{T} K: {num(k(f'particle_max_diameter_um_T{T}', {}).get('10ms'))} / "
            f"{num(k(f'particle_max_diameter_um_T{T}', {}).get('25ms'))}" for T in (3500, 5000, 8000))])


@section("Benchmarks against published measurements", "14_benchmarks.py, 15_gold_copper.py")
def _bench():
    vp = k("benchmark_vapor_pressure_ratio_range")
    if vp is None:
        return missing("14_benchmarks.py")
    s = [stamp("benchmark_vapor_pressure.csv", "benchmark_eaf_dust.csv", "gold_copper_benchmark.csv"), "",
         "Vapor pressure, model / literature (Jia et al. 2013), 800-1300 C: " +
         ", ".join(f"{e} {v[0]:.2f}-{v[1]:.2f}" for e, v in vp.items()),
         "", "EAF dust reduced with coke at 1,300 C (Chang et al. 2022); measured Zn removal 98.8 / 88.5 / ~50%, "
         "Fe metallization >90% at C/O 0.8 and <=10% at 0.16:"]
    e = k("benchmark_eaf_dust_1300C")
    if e:
        s.append(table(pd.DataFrame(e)))
    g = csv("gold_copper_benchmark.csv")
    if g is not None:
        s += ["", "Distribution between liquid iron and copper, 1,373 K (Yamaguchi et al. 2006):", table(g)]
    return "\n".join(s)


@section("Gold between the iron and copper bands", "15_gold_copper.py")
def _gold():
    g = csv("gold_copper_ladder.csv")
    if g is None:
        return missing("15_gold_copper.py")
    au = g[g.element == "Au"] if "element" in g else g
    cols = [c for c in au.columns if c == "scenario" or c.startswith("band_") or c == "main_band"]
    return "\n".join([stamp("gold_copper_ladder.csv"), "", "Share of gold per band:", table(au[cols])])


@section("What one city landfill holds (2.3 Mt, median US landfill)", "16_landfill_inventory.py")
def _landfill():
    t = csv("landfill_inventory.csv")
    if t is None:
        return missing("16_landfill_inventory.py")
    cols = [c for c in ("element", "stream", "form", "captured", "refining_yield", "theoretical_lb", "practical_lb")
            if c in t]
    return "\n".join([stamp("landfill_inventory.csv"), "",
                      "Pounds per landfill: theoretical = all of it; practical = captured in its band x "
                      "established refining yield.",
                      "stream = the band(s) the element is recovered from; D = D1 + D2.", table(t[cols])])


@section("Catalysts", "17_catalysts.py")
def _cat():
    if k("catalyst_lifetime_s_2890K") is None:
        return missing("17_catalysts.py")
    return "\n".join([
        stamp("catalyst_survival.csv", "catalyst_damkohler_hot.csv", "catalyst_carbothermic_sio.csv"), "",
        "Lifetime of a catalyst in the hot zone at 2,890 K (s): " +
        ", ".join(f"{n} {num(v)}" for n, v in k("catalyst_lifetime_s_2890K").items()),
        "Damkohler number of CF4 destruction, 25 ms: " +
        ", ".join(f"{T} K {num(v)}" for T, v in k("catalyst_damkohler_CF4").items()),
        "Carbon as a reagent (not a catalyst) lowers silica vaporization: " + "; ".join(
            f"p_SiO {r['p_SiO_atm']} atm at {num(r['T_with_carbon_K'])} K with carbon vs "
            f"{num(r['T_silica_alone_K'])} K alone" for r in k("carbothermic_sio_T_K", []))])


@section("Robustness: 5,000 random landfills (Monte Carlo sweep)", "06_sweep.py, 12_sweep_analysis.py")
def _sweep():
    bp = csv("sweep_5000_by_pressure.csv")
    sw = csv("sweep_5000.csv")
    if bp is None or sw is None:
        return missing("06_sweep.py --samples 5000 && python 12_sweep_analysis.py --samples 5000")
    s = [stamp("sweep_5000.csv", "sweep_5000_by_pressure.csv"), ""]
    ok = sw["error"].isna().sum() if "error" in sw else len(sw)
    s.append(f"Feeds: {len(sw):,}; completed: {ok:,}.")
    if "steps_certified" in sw:
        s.append(f"Equilibrium states: {int(sw.steps.sum()):,}; certified (Result 2 certificate): "
                 f"{int(sw.steps_certified.sum()):,}; solved by the Cantera backup: {int(sw.steps_cantera.sum()):,}.")
    s += ["", "By pressure:", table(bp), "", "Claims (a 'gold band' collects >= 10% of the gold; the 95% bound is "
          "the rule of three, 3/n, when no failure is seen in n feeds that contain the metal):"]
    c = k("sweep_5000_claims", {})
    for el in ("Zn", "Hg", "Pb", "Cd"):
        v = c.get(f"{el}_in_gold_bands")
        if v:
            s.append(f"  {el}: in a gold band in {v['feeds_with_any']} of {v['feeds_containing']} feeds; "
                     f"max share {num(v['max'])}; 95% bound on the rate {num(v['rate_bound_95'])}")
    for key in ("Au_share_in_B", "Au_share_in_C", "Au_share_in_D1", "Au_share_in_D2"):
        v = c.get(key)
        if v:
            s.append(f"  {key}: median {pct(v['median'])}, 5th-95th percentile {pct(v['p05'])}-{pct(v['p95'])}")
    for key in ("Au_band_counts", "Pd_band_counts", "Pt_band_counts", "Ag_band_counts"):
        if key in c:
            s.append(f"  {key}: {c[key]}")
    return "\n".join(s)


@section("Rechecking: a second solver and a second database", "18_independent_verification.py")
def _verif():
    a, b = k("verification_independent_solver"), k("verification_independent_data")
    if a is None:
        return missing("18_independent_verification.py")
    s = [stamp("verification_independent_solver.csv", "verification_independent_data.csv"), "",
         f"Second solver (Cantera VCS, Smith & Missen) on {a['states']} states: converged on "
         f"{a['cantera_converged']}; same condensed phases in {a['same_phase_set']} of {a['both_converged']} where "
         f"both converged; max relative difference {num(a['max_rel_diff_condensed'])} (condensed), "
         f"{num(a['max_rel_diff_gas_major'])} (major gas species).",
         f"PARAMANU's own solver passed the certificate in {a.get('paramanu_raw_certified', '-')} of {a['states']} "
         f"states; states as used, certified: {a.get('final_certified', '-')}.",
         f"Second database (full NASA CEA, NASA-9) for {b['elements']} elements: same main band for "
         f"{b['same_main_band']}; median |dT50| {num(b['median_abs_T50_diff_K'])} K, max {num(b['max_abs_T50_diff_K'])} K.",
         ""]
    d = csv("verification_independent_data.csv")
    if d is not None:
        s.append(table(d))
    return "\n".join(s)


@section("Reproducibility on another machine", "19_reproducibility.py")
def _repro():
    r = k("reproducibility")
    if r is None or not (RES / "log_19_reproducibility.txt").exists():
        return missing("19_reproducibility.py --samples 5000 --check 20")
    return "\n".join([stamp("log_19_reproducibility.txt"), "",
                      f"{r['feeds_checked']} sweep feeds recomputed from their seeds, {r['metrics_compared']} "
                      f"metrics each: largest absolute difference {num(r['max_abs_diff'])} ({r['worst_metric']}); "
                      f"main bands identical: {r['same_main_bands']}."])


@section("Adversarial falsification search", "20_falsification.py")
def _fals():
    f = k("falsification")
    if f is None or not (RES / "falsification.csv").exists():
        return missing("20_falsification.py  (about 6,600 ladders: use a cloud server)")
    s = [stamp("falsification.csv"), "",
         "Differential evolution over 56 inputs (masses x1/3-x3, traces and Hg x1/6-x6, pre-treatment 0-30%,",
         "pressure, every activity coefficient, chloride data), rewarded for putting the metal in a band",
         "that collects >= 10% of the gold. Falsified if the share exceeds the threshold.", ""]
    for claim in ("zinc", "mercury", "cadmium", "lead"):
        v = f.get(claim)
        if v:
            s.append(f"  {claim:8s}: {v['evaluations']:,} feeds tried; worst share in gold bands "
                     f"{num(v['worst_share_in_gold_bands'])} (threshold {v['threshold']}); "
                     f"{'FALSIFIED' if v['falsified'] else 'holds'}; smallest T50 gap to gold "
                     f"{num(v['smallest_T50_gap_K'])} K")
    return "\n".join(s)


@section("Which uncertain inputs matter (Sobol indices)", "21_global_sensitivity.py")
def _sobol():
    g = k("global_sensitivity_top")
    if g is None or not (RES / "global_sensitivity.csv").exists():
        return missing("21_global_sensitivity.py --samples 5000")
    s = [stamp("global_sensitivity.csv"), "",
         "First-order Sobol index = share of an output's variance that one input explains alone.", ""]
    for name, v in sorted(g.items()):
        tot = v.get("sum_all_first_order")
        top = ", ".join(f"{i} {x:.2f}" for i, x in sorted(v.items(), key=lambda kv: -kv[1])
                        if i != "sum_all_first_order")
        s.append(f"  {name}: {top}  (sum of all first-order indices {tot})")
    return "\n".join(s)


@section("Torch-gas dilution and the margin of the Band D split", "22_dilution_and_margin.py")
def _dilution():
    d, m = k("dilution_argon"), k("band_split_margin")
    if d is None or m is None:
        return missing("22_dilution_and_margin.py")
    s = [stamp("dilution_argon.csv"), "",
         "Default feed with argon added (moles per mole of the heap's own gas):", table(pd.DataFrame(d)), "",
         f"Band D split margin, for the lead feed the adversarial search brought closest: 99.9% of the gold has "
         f"condensed by {num(m['gold_999_condensed_by_K'])} K, the first 0.1% of the lead condenses at "
         f"{num(m['lead_first_001_condensed_at_K'])} K; the 1,300 K boundary sits in a {num(m['gap_K'])} K gap."]
    return "\n".join(s)

@section("Energy self-sufficiency: own fuel plus sale of recovered elements", "23_self_sufficiency.py")
def _selfsuff():
    d = k("self_sufficiency")
    if d is None:
        return missing("23_self_sufficiency.py")
    top = ", ".join(f"{e} ${v:,.1f}" for e, v in sorted(d["top_revenue"].items(), key=lambda x: -x[1]))
    cols = ["energy_case", "fuel_case", "MWh_needed", "MWh_from_own_fuel", "MWh_to_buy",
            "sales_share_at_0.10", "sales_share_at_0.05", "own_fuel_plus_sales_share_at_0.05",
            "break_even_price_per_kWh"]
    s = [stamp("self_sufficiency.csv"), "",
         f"Saleable products per tonne excavated (spreadsheet prices): ${d['revenue_per_t']:,.1f}; largest: {top}.",
         "Energy account per tonne (electricity $/kWh 0.10 and 0.05):",
         table(pd.DataFrame(d["cases"])[cols])]
    return "\n".join(s)

@section("Heat recovery, emissivity, modules and grinding", "24_heat_recovery_and_scale.py")
def _heatrec():
    d = k("heat_recovery")
    if d is None:
        return missing("24_heat_recovery_and_scale.py")
    lo, hi = d["steam_electricity_MWh_per_t"]
    s = [stamp("heat_recovery_self_sufficiency.csv"), "",
         f"Condenser-stage heat A-E: {d['stage_heat_MWh_per_t']} MWh/t; as electricity via boiler-wall steam "
         f"(60-70% captured, 30-35% cycle): {lo}-{hi} MWh/t ({d['steam_MW_1000tpd'][0]}-{d['steam_MW_1000tpd'][1]} MW at 1,000 t/day).",
         "Hot-zone emissivity (1,000 t/day, 1 atm):", table(pd.DataFrame(d["emissivity"])),
         "Parallel modules:", table(pd.DataFrame(d["modules"])),
         f"Grinding the mineral fraction to 20 um: {d['grinding_kWh_per_t']} kWh/t ({d['grinding_share_of_gross']:.1%} of the gross enthalpy).",
         "Self-sufficiency with steam recovery (power at 5 c/kWh):", table(pd.DataFrame(d["self_sufficiency"]))]
    return "\n".join(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fingerprint", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    fp = fingerprint()
    if a.fingerprint:
        print(fp)
        return
    head = ["PARAMANU Reclaimer - Results".center(W), "=" * W, "",
            f"Generated: {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by simulation/tools/write_results.py",
            f"Code fingerprint: {fp}  (python simulation/tools/write_results.py --fingerprint)",
            "",
            "Every number below was computed by the scripts in simulation/scripts and read from",
            "simulation/results. Nothing is typed by hand. To reproduce, see HOWTOREPLICATE.txt.",
            "One 'feed' = one wet tonne of excavated landfill residue (default composition in",
            "simulation/paramanu_sim/feed.py). Default pressure 1 atm.", ""]
    body = []
    for i, (title, script, fn) in enumerate(SECTIONS, 1):
        body += ["", "-" * W, f"{i}. {title}", f"   Script: simulation/scripts/{script}", "-" * W]
        try:
            body.append(fn())
        except Exception as e:                       # noqa: BLE001 - a broken section must not hide the rest
            body.append(f"Could not be written ({type(e).__name__}: {e}). Rerun {script}.")
    corr = ["", "-" * W, f"{len(SECTIONS) + 1}. Corrections log (fixes that changed results)", "-" * W]
    for date, what, detail in CORRECTIONS:
        corr += [f"{date}  {what}"] + ["    " + line for line in _wrap(detail, W - 4)]
    Path(a.out).write_text("\n".join(head + body + corr) + "\n")
    print(f"wrote {a.out} ({len(SECTIONS)} sections, fingerprint {fp})")


def _wrap(text, width):
    import textwrap
    return textwrap.wrap(text, width)


if __name__ == "__main__":
    main()
