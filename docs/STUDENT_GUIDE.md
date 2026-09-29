# Redo the proof: a student's guide to PARAMANU

This guide lets you check every claim of the PARAMANU paper yourself: first
with pencil and paper, then with one command, against a stated expected
output. You need school chemistry (moles, Gibbs energy, equilibrium) and a
little calculus. Nothing here asks you to trust the authors.

The evidence comes in three kinds, and each can only show certain things:

| Kind | What it can show | What it cannot show |
|---|---|---|
| **Proofs** (Results 1-7) | What physics permits and forbids, for any plant | That a particular plant works |
| **Simulation** (NASA data, Gibbs minimization) | What accepted thermochemistry predicts for this feed | Anything the model leaves out (kinetics, non-ideal alloys, missing species) |
| **Benchmarks** (published measurements) | Whether the same code predicts real, measured systems | The PARAMANU reactor itself, which has not been built |

Only experiments on a real reactor can prove the process; the paper's
research agenda (R1-R9) lists them.

---

## 0. Set up (10 minutes)

```bash
git clone https://github.com/syncaissa/paramanu-reclaimer
cd paramanu-reclaimer/simulation
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                      # every test must pass before you trust any number
cd scripts
```

Every script writes CSV tables and figures to `simulation/results/` and its
headline numbers to `results/key_numbers.json`. The expected values below are
the ones in the published `key_numbers.json`.

---

## 1. Every atom is accounted for (Result 1)

**Claim.** In a sealed reactor with labelled outlets, the moles of each
element that enter equal the sum over the outlets.

**By hand.** Chemical reactions rearrange atoms but never create or destroy
them. If no path leads to the air, every atom that enters leaves through a
labelled outlet.

**Check.** `python 02_ladder.py`, then open `results/ladder_band_grams.csv`:
for each element, the grams in all bands plus the gas equal the grams fed.
The test `test_mass_balance` checks it to 1 part in 1,000 on a coarse ladder;
each equilibrium balances every element above one part per million of the gas
to better than 1e-4 (see `18_independent_verification.py` and the paper's
Rechecking the Computation section for how this was checked).

**Try.** Delete one band column and see the balance fail. A real plant's
first acceptance test is exactly this sum on measured outlets.

---

## 2. The equilibrium exists and is unique (Result 2)

**Claim.** For fixed T and P there is exactly one equilibrium gas composition,
and it is described by one number per element, the *element potential*
lambda_i, through

    ln x_k = a_k . lambda - g_k - ln(P / 1 atm)

where `a_k` counts the atoms in species k and `g_k = G_k / RT` comes from the
NASA tables.

**Why it matters.** The solver's answer is *the* equilibrium, not one of
several. And the formula above lets you compute the amount of *any* species
from a handful of lambdas; the trace-metal chemistry (Section 8) is built on it.

**Check.** In Python, from `simulation/`:

```python
import cantera as ct, numpy as np
from paramanu_sim.feed import make_feed
from paramanu_sim.equilibrium import equilibrate
eq = equilibrate(make_feed().element_moles, 2200.0, ct.one_atm)
th = eq.thermo; th.gas.TP = 2200.0, ct.one_atm
N = sum(eq.gas.values())
for name in ("CO", "H2", "SiO", "Fe"):
    k = th.gas.species_index(name)
    pred = sum(c * eq.potentials[e] for e, c in th.gas.species(name).composition.items()) \
           - th.gas.standard_gibbs_RT[k]
    print(name, np.log(eq.gas[name] / N), pred)      # the two numbers agree to ~1e-10
```

---

## 3. When a dilute element condenses (Result 3)

**Claim.** An element at gas mole fraction y starts to condense where its
partial pressure meets its vapor pressure, `y P = p_sat(T_c)`; approximately

    1/T_c = 1/T_b - (R / dH_vap) ln(y P / P0)

**By hand (iron).** T_b = 3139 K, dH_vap = 349 kJ/mol. Just above its onset,
iron atoms are y = 8.52e-3 of the gas at 1 atm (print `eq.gas["Fe"] / N` at
2340 K with the snippet of Section 2). Then
1/T_c = 1/3139 - (8.314/349000) ln(8.52e-3) = 3.1857e-4 + 1.1352e-4 = 4.3209e-4,
so **T_c = 2314 K**. The paper's Result 3 table gives 2315 K (closed form),
2330 K (exact condition) and 2320 K (full simulation, 10 K steps): the closed
form is low by about 15 K because it treats dH_vap as constant.

**Check.** `python 07_theory_checks.py`: `theory_onset_max_abs_diff_K` is the
largest gap between the closed form and the simulation (expected: 18 K).

**Try.** Raise the pressure in the formula. y P grows, so T_c rises: every band
moves up with pressure. The 5,000-feed sweep (Section 9) shows exactly this.

---

## 4. What physics can and cannot separate (Result 4)

**Claim.** Splitting two elements of relative volatility alpha into products
of purity p needs at least `N_min = ln[p^2/(1-p)^2] / ln(alpha)` ideal stages
(the Fenske equation).

**By hand (gold from iron).** alpha = 1.43, p = 0.99:
N_min = ln(0.99^2 / 0.01^2) / ln(1.43) = ln(9801) / 0.3577 = 9.19 / 0.3577 = 25.7,
so 26 stages. Condensation alone will not split gold from iron; refining must.
Zinc from iron (alpha ~ 8e7 at 1500 K): N_min = 9.19 / 18.2 = 0.5, one stage.

**Check.** `python 07_theory_checks.py`, table `theory_relative_volatility.csv`.

---

## 5. How briefly the heap must be hot (Result 5)

**Claim.** A batch of mass m radiates its own energy in
`tau = e m / [eps sigma (36 pi)^(1/3) V^(2/3) (T^4 - Tw^4)]`, V = nu m R T / P.

**By hand (one tonne at 1 atm).** e = 10.2 MJ/kg, nu = 36.5 mol/kg, T = 2890 K,
eps = 0.3, Tw = 600 K.
V = 36,500 x 8.314 x 2890 / 101,325 = 8,655 m^3.
Area = (36 pi)^(1/3) x V^(2/3) = 4.836 x 421.6 = 2,039 m^2.
Q = 0.3 x 5.67e-8 x 2,039 x (2890^4 - 600^4) = 2.42e9 W.
tau = 1.02e10 J / 2.42e9 W = **4.2 s**. A slowly cooled sealed batch is impossible.

**Check.** `python 08_reactor_design.py`: `design_batch_tau_1t_1atm_s` = 4.23;
`design_batch_tau_scaling_exponent` = 0.333 (the m^(1/3) law);
`design_flow_max_residence_s_1000tpd_loss10pct` = 0.025 (25 ms).

---

## 6. Separation itself is cheap (Result 6)

**Claim.** Unmixing needs at least `W_min = -R T0 sum_i n_i ln x_i`.

**Check.** `python 07_theory_checks.py`: `theory_min_separation_work_MWh` = 0.067
MWh per tonne, `theory_min_work_share_of_vaporization` = 0.023 (2.3%). The
energy goes into heating and wall losses, not into the separation.

---

## 7. The heap forgets what it was (Result 7)

**Claim.** At fixed T and P the equilibrium depends only on the element totals,
not on the molecules the atoms arrived in. PVC, pharmaceuticals and PFAS with
the same elements end in the same gas.

**By hand.** The minimization of Result 2 sees the feed only through the
element balances b. Two feeds with the same b have the same problem, hence
(uniqueness) the same answer.

**Check.** `python 13_breakdown.py`. Three starts with identical atoms (bare
atoms; naphthalene, biphenyl, phenol, CF4, CCl4, phosgene, chloromethane; and
monomer-like molecules) give the same state:
`breakdown_max_rel_diff_between_starts` ~ 3e-9. In the real heap at 2890 K,
`breakdown_fraction_2890K` gives naphthalene 1e-28, benzene 1e-18, CF4 1e-38,
CCl4 2e-26, phosgene 6e-16.

**Try.** Add your own molecule to `HARD` in the script (any species in
Cantera's `nasa_gas.yaml`) and watch it vanish at 2890 K.

---

## 7b. How fast waste comes apart

Result 7 says where the heap ends up, not how fast. Two hand calculations
show that chemistry is fast and grain size is what matters.

**A molecule (CF4, the hardest PFAS end-product).** Measured rate
(Modica & Sillers 1968): k = 0.339 (T/298)^-4.64 exp(-512,200/RT) [M],
with [M] = P/(k_B T) = 2.53e18 molecules/cm^3 at 2900 K and 1 atm.
(2900/298)^-4.64 = 2.6e-5; exp(-512,200/(8.314 x 2900)) = 6.0e-10;
k = 0.339 x 2.6e-5 x 6.0e-10 x 2.53e18 = 1.3e4 per second, so the lifetime is
**75 microseconds**; a 25 ms hot zone lasts 330 lifetimes. Redo it at 2200 K:
the lifetime is 14 ms, so cold spots, not the average temperature, decide.

**A mineral grain (silica).** Heat flows in by conduction, q = dS / r with
dS = integral of k dT (Chen 1988). Heating (dh = 3.44 MJ/kg) at fixed size
and then vaporizing (L = 12.39 MJ/kg) while shrinking gives
t = rho d^2 (dh/12 + L/8) / dS. With rho = 2200 kg/m^3, d = 10 um and
dS = 304 W/m (air, 2900 -> 3500 K):
t = 2200 x 1e-10 x (2.87e5 + 1.55e6) / 304 = **1.3 ms**. Double d and t
quadruples. Measured: 30 um silicon grains evaporate 90% in an induction
plasma, 60 um grains 30-40% (Gitzhofer 1996), so this formula is optimistic.

**Check.** `python 13_breakdown.py`: `particle_max_diameter_um_T3500`,
`silica_heat_and_vaporize_MJ_per_kg`.

---

## 7c. What a catalyst can and cannot do (Result 8)

**By hand, the proof.** K = exp(-dG/RT) depends only on the Gibbs energies of
reactants and products. In transition-state theory k_f ~ exp(-(G_ts - G_R)/RT)
and k_r ~ exp(-(G_ts - G_P)/RT); a catalyst lowers G_ts, which multiplies both
by the same factor, so k_f / k_r = exp(-(G_P - G_R)/RT) = K is unchanged.

**By hand, the need (Damkohler number).** Da = residence time / reaction time.
CF4 lives 80 microseconds at 2,890 K, the hot zone lasts 25 ms: Da = 0.025 /
8.0e-5 = 314. A catalyst can only raise Da; at 314 the reaction is already
complete.

**By hand, survival (Hertz-Knudsen).** J = p_sat sqrt(M / (2 pi R T)). Nickel
at 2,890 K: p_sat = 2.62e4 Pa, M = 0.0587 kg/mol, so
J = 2.62e4 x sqrt(0.0587 / (2 pi x 8.314 x 2890)) = 16.3 kg/m^2/s, and a 5 nm
particle (rho = 7,810 kg/m^3) lasts t = rho r / J = 7810 x 5e-9 / 16.3 =
**2.4 microseconds**.

**Check.** `python 17_catalysts.py`: `catalyst_lifetime_s_2890K`,
`catalyst_damkohler_CF4`, `carbothermic_sio_T_K` (carbon lowers the temperature
at which silica vapor reaches 0.5 atm from 3,116 K to 1,955 K).

---

## 8. Trace metals with full chemistry

Gold, silver, palladium, platinum, cadmium, tin and other metals are at parts
per million, and most are missing from the standard NASA subset. They are
modelled in `paramanu_sim/trace_chem.py`:

1. **Data** (`paramanu_sim/trace_thermo.py`): NASA CEA and Burcat polynomials;
   AgCl, AuCl and CdCl2 computed from measured molecular constants by
   statistical mechanics (as NIST-JANAF does); Au2Cl2, Au2Cl6 and PtCl2 from
   measured reaction Gibbs energies. Every species carries its source.
2. **Method (dilute limit).** A trace does not change the major-element
   equilibrium, so the lambdas of Result 2 are fixed and the trace's own
   lambda_X solves one equation: its element balance over its gas species,
   its solution in each condensing metal, and any pure phase.

**Checks** (`pytest tests/test_trace.py`):

* every data record reproduces its own stated heat of formation (this caught
  two bad records in the source file, PtH and SbF, now excluded with reasons);
* statistical mechanics reproduces tabulated entropies (AgCl 245.91 vs 245.92
  J/mol/K; HCl 186.74 vs 186.90);
* vapor pressures hit the boiling points of Au, Ag and Pt;
* **the dilute-limit solver matches the full solver**: lead near its
  condensation point (0.11447 gaseous in both) and nickel dissolving in liquid
  iron (0.2475 in both).

**Try.** Run the ladder with the three data sets and compare where gold goes:

```python
from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
for ds in ("least_volatile", "central", "most_volatile"):
    lad = run_ladder(make_feed(), dT=50.0, trace_model="chemistry", trace_data=ds)
    print(ds, lad.recovery_table().loc["Au"].round(3).to_dict())
```

---

## 9. Robustness: 5,000 random landfills

`python 06_sweep.py --samples 5000` (about 22 minutes on 13 cores; see
`cluster/`), then `python 12_sweep_analysis.py --samples 5000`.

**The rule of three.** If a failure is never seen in n independent trials, its
rate is below 3/n with 95% confidence. Count only the trials that can fail.
Zinc and mercury are present in all 5,000 feeds and reached a gold-collecting
band in none, so the rate is below 3/5000 = 0.06%. With 24 feeds the bound
would only be 12.5%.

**A lesson in method.** An earlier version of the feed model gave the soil no
zinc or lead, so high pre-treatment removed them entirely; only 971 of 5,000
feeds contained them, and the first analysis still divided by 5,000 and
claimed 0.06% (the honest bound was 0.31%). Feeds without zinc cannot put zinc
in the gold band, so they are not trials. Always ask what the denominator is.
The feed now carries measured heavy metals in its fines (Vollprecht et al.
2020), and every feed contains them.

**Try.** Run `--samples 200` and compare the bound and the percentile ranges
with the published 5,000.

---

## 10. Benchmarks: the code against published measurements

`python 14_benchmarks.py`

* **Vapor pressures of lead and tin** (Jia et al. 2013, Table 4): the model is
  within 3% for lead and 9-18% for tin, 800-1300 C.
* **Steel-mill dust with coke** (Chang et al. 2022): iron metallization follows
  the measured pattern (above 90% at C/O 0.8, near zero at 0.16). Zinc: the
  equilibrium limit is full removal; coke pellets reach 50-99% because solid
  carbon reacts slowly, while pellets whose reductant is released as gas reach
  98% even at C/O 0.16. Equilibrium is the ceiling, and a gas-phase reductant
  (as in the plasma heap) reaches it.

**Try.** Find another published equilibrium experiment and add it as case D.
That is how this model should be attacked.

---

* **Gold between iron and copper** (Yamaguchi et al. 2006, 1373 K): the
  distribution ratio of a dilute solute between two liquids is
  L = (gamma in Cu / gamma in Fe) x (M_Cu / M_Fe). With gamma_Au = 17.1 in
  iron (Nagamori & Kameda 1968) and 0.05 in copper (Yazawa et al. 1975):
  L = (0.05/17.1) x 1.14 = **0.0033**, measured 0.0071-0.013. Right direction,
  2-4 times too strong. `python 15_gold_copper.py` does this and then runs the
  ladder.

## 11. Rechecking the computation: check the checker

The sweep shows the claims survive variation *if the model is right*. This
chapter tests the model itself (paper, Section "Rechecking the Computation").

**A certificate for any equilibrium state.** Result 2's dual form gives a test
that does not trust the solver. A state is the equilibrium if one vector of
element potentials lambda makes

    ln x_k = a_k . lambda - g_k - ln(P/P0)   for every gas species k
    a_c . lambda = g_c                        for every solid/liquid present
    a_c . lambda <= g_c                       for every solid/liquid absent
    sum of atoms of each element = feed       (Result 1)

`equilibrium.certify(eq, element_moles)` fits lambda to the amounts by least
squares and checks all four to 1e-4. Try it:

```python
from paramanu_sim.feed import make_feed
from paramanu_sim.equilibrium import equilibrate, certify
f = make_feed()
eq = equilibrate(f.element_moles, 1800.0)
print(eq.solver, certify(eq, f.element_moles))       # passes
eq.condensed.pop(next(iter(eq.condensed)))           # delete one phase
print(certify(eq, f.element_moles))                  # fails: the element balance no longer closes
```

**What it caught.** (1) Our solver failed to converge at 43 of 229 ladder
steps below 1,850 K, because parts-per-billion remnants were solved together
with major elements; the ladder now places elements below 1 ppm of the gas
with the dilute-limit solver (Result 3). (2) Cantera's solver, used as a
backup, reported convergence at 0.1 atm for states that are not the
equilibrium (graphite beside steam with no CO; zinc sulfate); used blindly,
they put zinc and lead in the gold bands' neighbours in 183 feeds. (3) Our
solver left graphite out in rare carbon-rich states at 0.1 atm; the NASA CEA
phase-set loop (`gibbs.refine`) now adds it. Lesson: two solvers agreeing is
evidence, a solver saying "converged" is not, and the certificate decides.

**The other checks** (all in `scripts/`):

* `18_independent_verification.py`: a second solver (Cantera VCS) on every
  state, and a second database (the full NASA CEA thermo.inp, NASA-9 fits).
* `20_falsification.py`: an optimizer (differential evolution) searches 56
  inputs for a feed that puts zinc, mercury, cadmium or lead in a gold band.
  About 6,600 ladders: run it on a cloud server (`cluster/runpod/run_job_on_runpod.sh`).
* `21_global_sensitivity.py`: Sobol indices from the sweep's own feeds: which
  uncertain input drives each result.
* `19_reproducibility.py`: recompute 20 sweep feeds from their seeds on your
  machine and compare with the published table.
* `docs/PREREGISTRATION.md`: the model's predictions for the first
  experiments, with the results that would count against it, fixed before
  any measurement.

**Try.** Loosen the certificate's tolerance to 1e-2 and count how many states
pass that should not; tighten it to 1e-6 and see which fail, and why.

---

## 12. How to break it (for skeptics)

* Change the feed in `paramanu_sim/feed.py` (more PVC, more copper, less
  organics) and rerun `02_ladder.py`.
* Push the activity coefficients of gold in iron and copper to the measured
  extremes (`trace_gamma` in `run_ladder`).
* Use the `most_volatile` trace data set.
* Halve the temperature step (`09_convergence.py`).

If a claim of the paper fails under a realistic change, that is a result worth
reporting. Open an issue with the command you ran.
