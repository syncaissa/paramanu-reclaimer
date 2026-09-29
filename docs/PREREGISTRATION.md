# Pre-registered predictions for the first PARAMANU experiments

Registered: 2026-09-29, with the paper version that contains the section
"Rechecking the Computation". This file is deposited with a timestamped DOI
(for example on OSF or Zenodo) at submission; that deposit, and the public
git history, are the record that the predictions and passing marks below
were fixed **before** any measurement. Do not edit them; add results in a
new section at the end.

P1 and P2 are consistency checks (any real device must close its balances
and exceed the gross enthalpy); P3-P13 are the risky predictions.

Why: a result counts for the most when its passing mark was set before the
measurement (Nosek et al., PNAS 115 (2018) 2600, doi:10.1073/pnas.1708274114).
A model that could explain any outcome explains nothing.

## The test case

* **Feed:** the synthetic residue of `simulation/paramanu_sim/feed.py`,
  `make_feed()` (default composition, 5.2% pre-treatment, 250 kg water per
  wet tonne, trace metals at their default ppm). A real residue can be used
  instead if it is analysed first and the model rerun with its analysis
  *before* the experiment; the new predictions are then added here first.
* **Apparatus:** research questions R1, R2 and R4 of the paper: a sealed
  plasma reactor or arc furnace that takes the feed fully to gas, and a
  condenser train with collectors held at the band temperatures of the
  paper (A >= 2,600 K, B 2,000-2,600 K, C 1,600-2,000 K, D1 1,300-1,600 K,
  D2 1,000-1,300 K, E 400-1,000 K, cold end 300-400 K, then a mercury trap;
  `SIMULATED_BANDS` in `ladder.py`), at 1 atm and at 5 atm. Band D is split
  at 1,300 K because the adversarial search found feeds rich in organics
  whose gold reaches 1,300-1,600 K, while lead condenses only below 1,300 K.
* **A second feed, the adversary's:** the organic-rich feed on which the
  first design failed (`results/falsification.csv` of the pre-split run,
  worst lead case: paper x2.8, plastics x2.5, 1.17 atm). Predictions P5 and
  P13 apply to it.
* **Equilibrium check:** repeat at half the cooling rate. If a band's
  composition changes by more than its measurement error, that band is
  kinetically limited and its predictions below are not tested by that run.
* **Model version:** the git commit containing this file. Predictions come
  from `02_ladder.py`, `04_energy.py`, `06_sweep.py`/`12_sweep_analysis.py`
  (1 atm feeds) and `15_gold_copper.py`.

## Predictions and what would count against them

| # | Quantity | Prediction | Passes if | Counts against the model if |
|---|---|---|---|---|
| P1 | Element balance, every element >= 0.1% of feed mass (Result 1) | closes exactly | closes within 3 standard uncertainties | does not close: fix leaks/analysis first; no other result is valid until it does |
| P2 | Energy to bring the batch to all gas, 1 atm | >= 2.90 MWh per wet tonne (thermodynamic minimum, 2,889 K) | measured net energy >= 2.6 MWh/t | measured < 2.6 MWh/t (10% below a minimum): thermochemical data wrong |
| P3 | Iron in Band B is metal, not oxide (the waste is its own reductant) | 100% metallic | >= 90% of Band B iron metallic (XRD, chemical analysis) | < 50% metallic |
| P4 | Order of half-condensation temperatures, 1 atm | Fe 2,225 K > Au 2,075 K > Cu 1,700 K > Pb 1,025 K > Zn 675 K > Cd 475 K; Hg does not reach 50% condensed above 300 K | same order, and Fe, Cu, Pb, Zn each within +-150 K | Zn, Cd or Hg condenses above Au or Cu; or any of Fe, Cu, Pb, Zn off by more than 150 K |
| P5 | Zinc, mercury, lead in bands holding >= 10% of the gold | 0% (never in 5,000 simulated feeds; none found by the adversarial search) | < 1% of each | >= 1% of any: the central separation claim is falsified |
| P6 | Cadmium in bands holding >= 10% of the gold | <= 0.01% | < 0.1% | >= 0.1% |
| P7 | Gold in Bands B + C, 1 atm | 100% (5th percentile of simulated feeds 99.3%) | >= 95% | < 90% |
| P8 | Gold in Band B (iron band), 1 atm | 58% (36-82% across the uncertainty of the activity coefficients; simulated feeds 5th-95th percentile 40-83%) | 20-95% | outside 20-95%: the activity coefficient of gold in liquid iron is wrong (P11 decides) |
| P9 | Palladium and platinum in Band B | ~100% | >= 90% | < 70% |
| P10 | Raising pressure from 1 to 5 atm | gold's half-condensation temperature rises ~250 K; gold in Band B rises from 58% to ~84% | both rise | either falls (Result 3 predicts the sign from y P) |
| P11 | Activity coefficient of gold in liquid iron, 1,900-2,250 K (the input that explains ~86% of the variance of P8) | 1.4-2.3 (extrapolated from Nagamori & Kameda 1968) | 0.5-7 | outside 0.5-7: rerun `15_gold_copper.py` with the measured value; its result replaces P8 (declared here in advance) |
| P12 | CF4 fed with the residue, hot zone >= 2,600 K for 25 ms | destroyed; equilibrium fraction 1e-38, Damkohler number >= 53 | < 0.01% of the CF4 fed leaves the hot zone | >= 0.01%: hot zone not uniform or rate data wrong |
| P13 | Organic-rich adversary feed (above), 1.2 atm: gold in D1 and lead in D2 | gold ~11% in D1 with 0% of the lead; lead ~49% in D2 with 0% of the gold | < 1% of the lead in D1 and < 1% of the gold in D2 | >= 1% of either: gold and lead overlap in temperature and the split does not separate them |

## Reporting

All runs are reported, including failed and inconclusive ones, with the raw
analyses, in `results/experiments/` of the repository and in the paper's next
version. A prediction that fails is reported as failed; the model may then be
revised, but the revision is new work and is tested by new predictions
registered here before the next experiment.

## Results

(none yet)
