# PARAMANU Implementer's Guide

A step-by-step procedure for designing an Atomize-First plant, or a pilot, from
the results of the paper. Every step lists its inputs, the equation or program
that produces its output, and a worked example for **1,000 wet tonnes per day at
1 atm with the default feed**. Replace every default with your own site data.

Equation and result numbers refer to the paper (build it with `paper/build.sh`, which
writes `paper/output/PARAMANU_Reclaimer.pdf`; Section 4 "Design Principles from Established Thermodynamics" and
Section 6 "Computational Evidence").

> **What this guide can and cannot do.** It turns proven physics and validated
> simulation into a design procedure. It cannot replace experiments: kinetics,
> materials and real (non-ideal) alloys must be measured on a pilot. Step 9 lists
> the tests that decide whether a design works.

---

## 0. Set up the tools

```bash
git clone https://github.com/syncaissa/paramanu-reclaimer.git
cd paramanu-reclaimer/simulation
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest            # 38 tests must pass before you trust any result
```

## 1. Characterize the feed

**Input:** excavated residue after your chosen pre-treatment (the paper leaves
the extent of pre-treatment to you; it is encouraged because it saves energy).

**Do:**
1. Take composite samples across the area and depth of the landfill cell.
2. Measure moisture (drying at 105 °C), loss on ignition (organic content),
   major elements by X-ray fluorescence and trace elements by ICP-MS.
3. Enter the results in `paramanu_sim/feed.py`:
   - `DEFAULT_MASSES` - kg of each component per wet tonne
   - `COMPONENTS` - composition of each component (compounds and mass fractions)
   - `DEFAULT_TRACES_PPM` - trace metals in ppm of dry feed
   - `DEFAULT_MOISTURE_KG`

**Worked example:** 250 kg water and 711 kg dry residue per wet tonne; soil as
upper continental crust oxides (Rudnick & Gao 2003); gold 0.5 ppm.

## 2. Make hazards safe (mandatory)

- Discharge and dismantle batteries; their metal casings may go to the heap.
- Depressurize gas cylinders and aerosol cans; the metal may go to the heap.
- Divert anything flagged by radiation portal monitors to a licensed handler.
  Nuclear and radiological materials are outside the scope of PARAMANU.

## 3. Compute the all-gas state

```bash
cd scripts && python 04_energy.py
```

**Output** (`results/energy_envelope.csv`): all-gas temperature `T`, energy per
tonne, and gas moles. From these:

- specific energy `e` = energy / wet mass (J/kg)
- gas yield `nu` = gas moles / wet mass (mol/kg)

**Worked example (1 atm):** `T` = 2,890 K, `e` = 10.2 MJ/kg, `nu` = 36.5 mol/kg.

## 4. Choose the pressure

| Pressure | All-gas T | Hg left in gas | Hot volume |
|---|---|---|---|
| 0.1 atm | 2,630 K | ~100% | 10x larger |
| 1 atm | 2,890 K | ~51% | reference |
| 2 atm | ~2,970 K | ~22% | 2x smaller |
| 10 atm | 3,190 K | lower | 10x smaller |

Higher pressure shrinks the hot zone and helps mercury condense; it raises the
all-gas temperature slightly. **Worked example:** 1 atm in the hot zone, 2 atm
or more at the mercury trap.

## 5. Size the hot zone (Result 5)

For a continuous hot zone processing `m_dot` kg/s with gas residence time `t_r`,
the fraction of torch power lost to wall radiation is (paper Eq. 7):

```
Q/W = eps*sigma*(36*pi)^(1/3) * (m_dot*nu*R*T*t_r/P)^(2/3) * (T^4 - T_w^4) / (m_dot*e)
```

Then torch power `W = m_dot*e / (1 - Q/W)` and hot volume `V = m_dot*nu*R*T*t_r/P`.

```python
from paramanu_sim import theory
theory.flow_loss_fraction(mass_flow_kg_s=11.57, e_J_per_kg=10.2e6, gas_mol_per_kg=36.5,
                          T=2890, P=101325, residence_s=0.010)      # -> 0.049
```

**Worked example (1,000 t/day, `m_dot` = 11.57 kg/s, gas flow 100 m³/s):**

| Target loss | Residence `t_r` | Hot volume | Torch power |
|---|---|---|---|
| 3% | 5 ms | 0.5 m³ | 122 MW |
| 5% | 10 ms | 1.0 m³ | 124 MW |
| 10% | 25 ms | 2.5 m³ | 130 MW |

A **batch** design must instead satisfy paper Eq. 6: the whole batch radiates its
energy in `tau = E/Q` (4.2 s for 1 t at 1 atm, growing only as `m^(1/3)`), so
heating and quenching must take a small fraction of `tau`. Slow cooling of a
sealed batch is not feasible at any size.

## 6. Design the condenser train

```bash
python 02_ladder.py        # band temperatures and what each band collects
python 08_reactor_design.py  # heat duty per band
```

1. Place one collector per band along the gas path, at the band temperatures of
   the simulated ladder (paper Table 5): A >= 2,600 K, B 2,000-2,600 K,
   C 1,600-2,000 K, D 1,000-1,600 K, E 400-1,000 K, cold trap < 400 K.
2. Size each exchanger from its duty `Q` (`results/design_condenser_duty.csv`):
   `A = Q / (U * dT_lm)` with the heat-transfer coefficient `U` of your exchanger.
3. Where a band must be split further, the minimum number of ideal stages is the
   Fenske equation (paper Eq. 5), tabulated in `results/theory_relative_volatility.csv`.

**Worked example duties (1,000 t/day):** A 13.5 MW, B 28.4 MW, C 21.9 MW,
D 14.9 MW, E 15.7 MW, cold trap 5.4 MW. 42% of the heat is released above
2,000 K and is worth recovering to power.

## 7. Capture mercury

- Place a sulfur-impregnated carbon bed after the coldest collector; mercury
  leaves as HgS (stable storage form).
- Size it for the **full** mercury input: depending on feed and pressure, 5-100%
  of the mercury reaches this point (paper Sections 6.3 and 6.7).
- Check the mercury balance (paper Eq. 2) on every campaign.

## 8. Route each band to refining

| Band | Collects (default feed) | Route |
|---|---|---|
| A | W, Ti (TiC), Pt, part of Co, Pd, Au, Si | Refractory and precious-metal refining |
| B | Fe with Au, Pd, Co (and Ni, Cu with alloying); Al, Ca oxides | Smelt; electrorefine; precious metals from anode residue. **Gold cannot be separated from iron by condensation** (26 stages, Result 4) |
| C | Mg, Si, Ni, Cu, Sn | Cu from Ni by condensation (3.5 stages) or electrochemically |
| D | Na, K, Cl salts; S, Mn, Ag, In, Sb, Bi, Ga | Leach salts; recover silver |
| E | Zn, Pb, Cd, Li, F, P | Split Zn/Pb/Cd by condensation (1-5 stages) |
| Cold | water, carbon | Treat water to discharge limits |
| Gas | N2, H2, CO; mercury remainder | Cylinders; mercury trap |

Toxic products go to the stable forms of paper Table 3; anything not worth
purifying under the slider policy (paper Section 10) is vitrified.

## 9. Acceptance tests

A plant or pilot passes when:

1. **Mass closure:** every element balance closes within the measurement error (Eq. 2).
2. **Onset temperatures:** each metal collected as a pure phase starts condensing within the bounds of Result 3 (2% for mole fractions >= 1e-4).
3. **Band compositions:** agree with the model run on the *measured* feed; any gap is explained by alloying (compare `11_alloy_model.py`) or kinetics.
4. **Mercury:** outlet concentration below the permit limit.
5. **Energy:** measured energy per tonne and wall losses agree with Results 5 and 6.

## 10. Safety

- Relieve pressure only into closed capture volumes, never to air.
- Interlock torch power on vessel pressure and wall temperature.
- Keep radiation portal monitors at intake.
- Obtain NPDES (water) and RCRA (hazardous residue) permits, and air permits.

---

### Scaling your study on servers

```bash
OMP_NUM_THREADS=1 python scripts/06_sweep.py --samples 5000         # one server, all its CPUs
RAY_ADDRESS=auto python scripts/06_sweep.py --samples 20000 --backend ray   # cluster
```

See `simulation/cluster/README.md`. GPUs are used by `05_chamber.py --gpu`; the
equilibrium solver runs on CPUs.
