# PARAMANU Reclaimer

**Plasma-Assisted Recovery And Mining of Atoms, Neutralizing Urban-waste.**
*Paramāṇu* (परमाणु) is Sanskrit for the atom, the "ultimate particle".

Recycling today stops where sorting stops. PARAMANU starts there: the mixed
landfill residue that no sorter can separate flows through an airtight plasma
reactor with no process stack, is taken fully into the gas phase for tens of
milliseconds, and is separated element by element as it cools past condensers
held at falling temperatures. The metals were mined once; PARAMANU harvests
them again. This repository holds the paper,
the open simulation that tests it, the baseline economic model and the artwork.

## Start here

| File | What it is |
|---|---|
| [`AllExplainedHere.pdf`](AllExplainedHere.pdf) | Everything in the paper explained in detail and plain language: every idea, proof, calculation, number, check and correction, and where each lives in the repository (source: `docs/all_explained/`) |
| [`Results.txt`](Results.txt) | Every result in plain text, generated from the result files (never typed by hand), with a code fingerprint and a log of every correction |
| [`HOWTOREPLICATE.txt`](HOWTOREPLICATE.txt) | Step by step: from a fresh computer to the same numbers |
| [`docs/STUDENT_GUIDE.md`](docs/STUDENT_GUIDE.md) | Redo the proofs yourself, chapter by chapter, with exercises |
| [`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md) | The model's predictions for the first experiments, with pass/fail marks fixed before any measurement |

## What is here

| Folder | Contents |
|---|---|
| [`paper/`](paper) | LaTeX source, figures, bibliography and the build pipeline: `paper/build.sh` makes the PDF, HTML and Word versions in `paper/output/` |
| [`simulation/`](simulation) | Thermochemical equilibrium solver, condensation-ladder model, closed-form theory, twenty-four experiments, results, 38 tests, cluster and AI guides |
| [`docs/`](docs) | [Implementer's Guide](docs/IMPLEMENTERS_GUIDE.md): step-by-step design procedure with equations and a worked 1,000 t/day example |
| [`model/`](model) | Sort-First baseline mass, energy and economics spreadsheet and the script that generates it |
| [`art/`](art) | Lifecycle illustration |

## What the simulation shows (1 wet tonne of landfill residue)

| Claim | Result | Verdict |
|---|---|---|
| The whole residue can be turned into gas | All gas at 2,890 K (1 atm) | Supported |
| Elements separate into bands as the gas cools | Clear bands, at lower temperatures than boiling points suggest | Supported, revised |
| Precious metals are concentrated | Pd and Pt with iron; gold split between the iron and copper bands (median 60% / 34% over 5,000 feeds), 28-fold enriched in its main band's metal | Supported, revised |
| Toxic volatiles leave the precious-metal band | 5,000 feeds: no Zn, Hg or Pb in any band that collects gold (rate < 0.06% at 95% confidence), Cd at most 0.01%. An adversarial search broke the first design for lead (organic-rich feeds put gold into lead's band); splitting Band D at 1,300 K fixed it, because gold and lead never condense at the same temperature | Supported, revised |
| Mercury gathers at the cold end | 58% stays gaseous at 1 atm (10% at 5 atm, 100% at 0.1 atm); needs a dedicated trap | Revised |
| Bands sit at fixed temperatures | Every band moves with pressure; gold's main band is B at 1-5 atm but C or D1 at 0.1 atm, so run at 1 atm or above | Revised |
| The waste carries its own reducing agent | Iron 100% metallic with the organics, 43% without | Supported |
| Energy | 2.9 MWh per tonne to all-gas (10.5 was an upper bound) | Revised down |
| A sealed batch can be cooled slowly | Wall radiation exceeds batch energy within seconds; hot zone must last tens of ms | Not supported |
| Gold can be separated from iron by condensation | Relative volatility 1.43: 26 ideal stages; chemical refining needed | Not supported |

The solver is validated against 15 pure-element boiling points (median error
0.16%, max 2.3%) and against Cantera's gas equilibrium (agreement to 1e-8).
Eight design principles from established thermodynamics, each with its proof
(paper Section 4), bound what the design can achieve; each is checked against
the simulation and by the test suite. Paper Section 5 walks one parcel of
residue through a reference plant, ties each station to the result that governs
it, and answers the main engineering objections: why the chamber does not melt,
fume (the largest open risk), heat recovery as steam in boiler walls, parallel
modules, grinding, and slag/metal separation. Section 8 gives the energy account,
including when the plant can pay for its own energy.

**How the model itself was checked** (paper, "Rechecking the Computation"):
every one of the 570,000 equilibrium states of the sweep passes a
mathematical certificate derived from Result 2; a second, separately
written solver (Cantera VCS) and a second database (the full NASA CEA
database) give the same bands; an optimizer searched 56 inputs for feeds
that break the claims; Sobol indices show which uncertain input matters;
sweep feeds recomputed on another machine agree to 1e-13. These checks found
three solver defects and one design flaw, all fixed and listed in the
corrections log of `Results.txt`.

Simulations are evidence, not proof; the paper's research agenda lists the
experiments that must follow, and `docs/PREREGISTRATION.md` fixes in advance
what result would count against the model.

## Quick start

```bash
# simulation
cd simulation
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                       # 38 tests
./run_all.sh                 # all experiments -> simulation/results/ and ../Results.txt

# paper (needs TeX Live, latexmk, poppler-utils, pandoc >= 3, pdf2htmlEX)
cd ../paper && ./build.sh    # -> paper/output/{pdf,html,docx} and a Blogger-ready HTML
```

Large Monte Carlo sweeps on many servers: see [`simulation/cluster`](simulation/cluster).

## Scope and safety

Nuclear and radiological materials (uranium, thorium, plutonium, radium,
polonium, americium and radioactive isotopes) are deliberately excluded from
every list, model and figure, for security reasons and because they are not
expected in meaningful quantities. Radioactive items are removed before
processing and handed to licensed handlers.

## Author

Milind K. Patil, Syncaissa Systems Inc. — syncaissa@outlook.com
