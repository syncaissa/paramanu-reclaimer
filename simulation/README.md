# PARAMANU simulation: computational evidence for Atomize-First recovery

This package tests the claims of the PARAMANU Reclaimer paper against
established thermochemistry. It does **not** prove that a plant will work;
only experiments can do that. It shows what the laws of thermodynamics and
the standard NASA data predict for a sealed batch of landfill residue, where
the paper's claims hold, and where they do not.

## What it computes

| Paper claim | Experiment | Script |
|---|---|---|
| The solver reproduces known physics | Pure-element boiling points vs. CRC Handbook; gas equilibria vs. Cantera | `scripts/01_validate.py` |
| Elements condense in separable bands as the batch cools | Fractional condensation of the whole heap, 6000 K to 300 K | `scripts/02_ladder.py` |
| The heap carries its own reducing agent | Ladder with the organic fraction scaled x0 to x2 | `scripts/03_reductant.py` |
| Energy envelope | Enthalpy of the equilibrium state vs. temperature, pressure, pre-treatment | `scripts/04_energy.py` |
| The sealed chamber is buildable | Vessel volume, wall radiation, ionization (Saha, GPU-capable) | `scripts/05_chamber.py` |
| Conclusions are robust | Monte Carlo over feed, pre-treatment, pressure, trace activity | `scripts/06_sweep.py` |
| Results 3, 4, 6 of the paper | Closed-form condensation onset vs. simulation; relative volatility and Fenske stages; minimum work of separation | `scripts/07_theory_checks.py` |
| Result 5 of the paper | Batch time constant, continuous hot-zone loss vs. residence time, condenser duties | `scripts/08_reactor_design.py` |
| Numerics are converged | Ladder at 100, 50, 25, 12.5 K steps | `scripts/09_convergence.py` |
| Which inputs matter | One-at-a-time sensitivity (tornado) | `scripts/10_sensitivity.py` |
| Alloying | Ladder with an ideal liquid-metal solution | `scripts/11_alloy_model.py` |
| Each claim, tested over the sweep | Claim-by-claim outcomes, rule-of-three bounds, breakdown by pressure | `scripts/12_sweep_analysis.py` |
| Result 7: complexity is forgotten; how waste comes apart | Same state from three molecular starts; residual molecules in the heap; silica grain vaporization time vs size | `scripts/13_breakdown.py` |
| The code against measurements | Pb/Sn vapor pressures (Jia 2013); EAF dust carbothermic reduction (Chang 2022) | `scripts/14_benchmarks.py` |
| Gold between iron and copper | Measured Fe/Cu partition (Yamaguchi 2006) vs the activity coefficients used; gold's bands under measured and bracketed coefficients | `scripts/15_gold_copper.py` |
| What a city landfill holds | Theoretical and practically recoverable pounds of every element in the median US landfill (2.3 Mt) | `scripts/16_landfill_inventory.py` |
| Result 8: what catalysts can and cannot do | Catalyst survival at 2,890 K (Hertz-Knudsen), Damkohler numbers, carbon as a reagent for silica | `scripts/17_catalysts.py` |
| Is the model itself right? (a second solver, a second database) | Every ladder state recomputed with Cantera's VCS solver; the ladder recomputed with the full NASA CEA database (shipped in `paramanu_sim/data/nasa_cea_thermo.inp`) | `scripts/18_independent_verification.py` |
| Do results depend on the machine? | Sweep feeds recomputed from their seeds and compared with the published table | `scripts/19_reproducibility.py` |
| Can any feed break the claims? | Differential evolution over 56 inputs, rewarded for putting Zn, Hg, Cd or Pb in a gold band | `scripts/20_falsification.py` |
| Which uncertain input matters? | First-order Sobol indices from the sweep's feeds (given-data method) | `scripts/21_global_sensitivity.py` |
| Does torch gas shift the bands? How safe is the Band D split? | Default ladder with argon dilution; the closest adversarial lead feed at 12.5 K steps | `scripts/22_dilution_and_margin.py` |
| Can the plant pay for its own energy? | Own fuel plus the sale of recovered elements (spreadsheet prices) against the electricity it must buy; break-even power price | `scripts/23_self_sufficiency.py` |
| Can the condenser heat be used, and do the engineering objections hold? | Steam from boiler-wall condensers, emissivity up to 1, parallel modules, grinding energy, self-sufficiency with steam | `scripts/24_heat_recovery_and_scale.py` |

Outputs (CSV data, PDF/PNG figures and `key_numbers.json`) go to `results/`.
`tools/write_results.py` turns them into `../Results.txt`, the plain-text
record of every result, with a code fingerprint and a corrections log.

## How every equilibrium state is checked

`equilibrium.equilibrate` does not trust any solver. Each state must pass a
certificate derived from Result 2 (`equilibrium.certify`): one set of element
potentials must reproduce every gas amount, no absent solid or liquid may be
supersaturated, and every element must balance, all to 1e-4. The PARAMANU
solver is tried first; if its state fails, the NASA CEA phase-set loop
(`gibbs.refine`) adds the missing phase; then Cantera's VCS solver; then an
amount repair. The solver that produced each state and whether it was
certified are recorded (ladder `duties`: `solver`, `certified`). In the ladder,
elements below 1 ppm of the gas are placed by the dilute-limit solver of
Result 3 at the certified potentials of the others (`ladder.DILUTE_SHARE`).

## Method

* **Thermodynamic data:** NASA polynomials (McBride, Zehe & Gordon 2002) for
  ~430 gas species and ~250 condensed species over 24 elements, as shipped
  with [Cantera](https://cantera.org). Condensed species are used only inside
  their valid temperature windows.
* **Equilibrium solver** (`paramanu_sim/gibbs.py`): Gibbs-energy minimization
  for an ideal gas plus pure condensed phases. Gas-only states use the
  Newton iteration of Gordon & McBride (NASA RP-1311, the CEA algorithm);
  multiphase states solve the convex dual problem in the element potentials,
  recover phase amounts by non-negative least squares, and polish with the
  CEA Newton step (or, with solution phases, an exact solve of the equilibrium
  conditions). If it does not converge, the state is recomputed with Cantera's
  independent VCS multiphase solver (`equilibrate(..., fallback=True)`); each
  ladder step records which solver produced it. Element balances close to
  better than 1e-4 for every element above 1 ppm of the gas. Optional ideal liquid-metal
  solution (`metal_solution=True`) adds one convex constraint per solution.
* **Closed-form theory** (`paramanu_sim/theory.py`): vapor pressures from the
  same NASA data, condensation onset, relative volatility, Fenske stages,
  hot-zone design laws and the minimum work of separation.
* **Condensation ladder** (`paramanu_sim/ladder.py`): the batch is cooled in
  steps; whatever condenses is removed to the collector of that temperature
  band; the remaining gas carries on (fractional-condensation limit).
* **Trace metals** (Au, Ag, Pd, Pt, Sn, Sb, Cd, Co, Mn, Bi, In, Ga, W;
  `paramanu_sim/trace_chem.py`, the default): full chemistry in the dilute
  limit. The major-element equilibrium fixes the element potentials (Result
  2); each trace then solves one equation for its own potential over its gas
  species (atoms, chlorides, oxides), its solution in each condensing metal
  (measured Henrian activity coefficients, `data/trace_gamma.json`) and its
  pure phases. Checked against the full solver in `tests/test_trace.py`.
  Data (`paramanu_sim/trace_thermo.py`): NASA CEA and Burcat & Ruscic
  extracts (`data/trace_cea.inp`, `data/trace_burcat.thr`, produced by
  `tools/extract_trace_data.py`); AgCl, AuCl and CdCl2 from measured molecular
  constants by statistical mechanics (`data/trace_statmech.json`); Au2Cl2,
  Au2Cl6 and PtCl2 from measured reaction Gibbs energies
  (`data/trace_bracket.json`, used only in the `most_volatile` data set).
  Every species records its source. Nd has no data and keeps the earlier
  vapor-pressure model (`traces.py`, also available for every trace with
  `run_ladder(..., trace_model="vapor")`).
* **Particle heating** (`paramanu_sim/particle.py`): conduction-limited heating
  and vaporization of a grain, t = rho d^2 (dh/12 + L/8) / dS (Chen 1988),
  with the conductivity of equilibrium air (Gupta et al., NASA RP-1260).
* **Feed** (`paramanu_sim/feed.py`): proxy compositions for soil (upper
  continental crust, Rudnick & Gao 2003), soda-lime glass, a plastics mix,
  cellulose and metals; masses from the Sort-First baseline spreadsheet.
  Every number is a parameter; replace with site sampling data.

## Known limitations

0. **Trace-metal data are the weakest part.** Gold chlorides have no open
   tabulated data (AuCl is computed; +/-13 kJ/mol); gold's activity
   coefficient in iron is extrapolated (Nagamori & Kameda 1968) and in copper
   rests on one tabulated value; Pt in Fe/Cu and Pd in Cu are unmeasured and
   treated as ideal; traces dissolve only in condensing metals, not slag. The
   sweep brackets each of these.
1. Alloys are modelled as ideal solutions (or pure phases) and oxides as pure
   phases; non-ideal CALPHAD solution models would refine band compositions.
2. Equilibrium at every step: no nucleation or kinetics. Fast quenching can
   trap non-equilibrium products.
3. The ionization estimate is an upper bound (all atoms, single ionization,
   unit partition-function ratio).
4. Radiation uses a grey-gas emissivity of 0.1-0.3 and cooled walls at 600 K.
5. Security-sensitive elements are excluded by design (see the paper).

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                                  # 38 tests, ~30 s
cd scripts
python 01_validate.py && python 02_ladder.py && python 03_reductant.py
python 04_energy.py && python 05_chamber.py --gpu   # --gpu uses CuPy if present
python 06_sweep.py --samples 24                      # small; see cluster/ for large runs
python 12_sweep_analysis.py --samples 24             # test each claim over the sweep
```

Or run everything with `./run_all.sh`.

## Hardware

Equilibrium solves are CPU work (one 50 K-step ladder with full trace
chemistry takes about 3.5 core-seconds on a cloud server core and 16-26 s on
the 2-core workstation used here; the published 5,000-feed sweep took 22
minutes on 13 cores). Use the pinned versions in `requirements.txt`: with newer
SciPy/pandas some feeds stalled. Workers default to the CPUs the container
may actually use (cgroup quota), not the host's core count, and a sweep
checkpoints every finished feed to `results/sweep_<N>.partial.jsonl`, so
rerunning the same command after a crash resumes where it stopped. The log
gets timestamped `STATUS` lines (START, RESUMING, PROGRESS with ETA,
COMPLETE, FAILED); a log that ends without COMPLETE or FAILED means the
machine or process died at about the last timestamp.
Large Monte Carlo sweeps scale across many cores and machines with Ray
(`cluster/`). GPUs are used for the Saha ionization grids and are the natural
home for the next steps: CFD of the reactor and machine-learned potentials
for species missing from the NASA data. See `ai/` for how language models
can help without becoming part of the evidence.
