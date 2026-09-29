"""Extract the trace-metal thermodynamic records the simulation needs from the
full public source files, so the repository ships only what it uses.

Sources (download them yourself to re-run this script):
  * NASA CEA thermo.inp (McBride, Zehe & Gordon, NASA/TP-2002-211556; the
    open-source CEA release, github.com/nasa/cea, Apache-2.0).
  * Burcat & Ruscic, "Third Millennium Ideal Gas and Condensed Phase
    Thermochemical Database" (BURCAT.THR; free for non-commercial use with
    citation; commercial use needs the authors' permission).

    python tools/extract_trace_data.py thermo.inp BURCAT.THR

writes paramanu_sim/data/trace_cea.inp and paramanu_sim/data/trace_burcat.thr.
"""
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "paramanu_sim" / "data"
sys.path.insert(0, str(DATA.parents[1]))
from paramanu_sim.thermo import EQUILIBRIUM_ELEMENTS  # noqa: E402

TRACES = {"Au", "Ag", "Pd", "Pt", "Sn", "Sb", "Cd", "Co", "Mn", "Bi", "In", "Ga", "W"}
ALLOWED = {e.upper() for e in EQUILIBRIUM_ELEMENTS} | {t.upper() for t in TRACES}
# Burcat is used only where CEA has no data, and never for species the
# Burcat file itself labels as estimates.
BURCAT_ELEMENTS = {"AU", "PD", "PT", "SB", "BI"}
BURCAT_REJECT = ("PM3", "ESTIMATED", "ESTIMATE ", "SEMIEMPIRICAL", "SEMI-EMPIRICAL",
                 "HF298= N/A", "HF298=N/A", "HF298 = N/A")   # no heat of formation: H298 is a placeholder


# Records rejected after checking them (tests/test_trace.py compares every kept
# polynomial with the heat of formation stated in its own comment).
BURCAT_EXCLUDE = {
    "SbF": "polynomial gives H298 = -74.1 kJ/mol but the record states HF298 = -74.128 kcal/mol "
           "(-310.2 kJ/mol): a unit error in the source record",
}


def cea_records(path):
    """Yield (formula, lines) for each species record in a NASA-9 thermo.inp."""
    L = Path(path).read_text().splitlines()
    i = L.index("thermo") + 2
    while i < len(L):
        line = L[i]
        if not line.strip() or line.startswith(("!", "END")):
            i += 1
            continue
        try:
            nint = int(L[i + 1][:2])
        except (ValueError, IndexError):
            i += 1
            continue
        form = {}
        for k in range(5):
            s = L[i + 1][10 + 8 * k:18 + 8 * k]
            if s[:2].strip() and float(s[2:]) != 0:
                form[s[:2].strip().upper()] = float(s[2:])
        n = 3 if nint == 0 else 2 + 3 * nint
        yield form, L[i:i + n]
        i += n


def burcat_records(path):
    """Yield (formula, phase, lines) for each 4-line NASA-7 record in BURCAT.THR."""
    L = Path(path).read_text(errors="replace").splitlines()
    for i, line in enumerate(L[:-3]):
        if len(line) >= 80 and line[79] == "1" and L[i + 1][79:80] == "2" \
                and L[i + 2][79:80] == "3" and L[i + 3][79:80] == "4":
            form = {}
            try:
                for k in range(4):
                    s = line[24 + 5 * k:29 + 5 * k]
                    el, num = s[:2].strip().upper(), s[2:].strip()
                    if el and num and float(num) != 0:
                        form[el] = float(num)
            except ValueError:
                continue                          # malformed header: skip the record
            # comment block: the lines since the previous record
            j = i - 1
            while j >= 0 and not (len(L[j]) >= 80 and L[j][79] == "4"):
                j -= 1
            yield form, line[44], L[j + 1:i], L[i:i + 4]


def main(cea_path, burcat_path):
    DATA.mkdir(exist_ok=True)
    kept, cea_names = [], set()
    for form, lines in cea_records(cea_path):
        name = lines[0][:24].split()[0]
        if name.endswith(("+", "-")) or "E" in form:
            continue
        if form and set(form) <= ALLOWED and set(form) & {t.upper() for t in TRACES}:
            kept.append("\n".join(lines))
            cea_names.add(frozenset(form.items()))
    head = ("! Extract of the NASA CEA thermodynamic database (thermo.inp; McBride, Zehe &\n"
            "! Gordon, NASA/TP-2002-211556; github.com/nasa/cea, Apache-2.0). Only species\n"
            "! containing a PARAMANU trace metal are kept; records are unchanged.\n"
            "! Produced by tools/extract_trace_data.py.\nthermo\n"
            "    200.00   1000.00   6000.00  20000.   extract\n")
    (DATA / "trace_cea.inp").write_text(head + "\n".join(kept) + "\nEND PRODUCTS\nEND REACTANTS\n")

    out, n_b = [], 0
    for form, phase, comment, lines in burcat_records(burcat_path):
        if not form or not set(form) <= ALLOWED or not set(form) & BURCAT_ELEMENTS:
            continue
        if "C" in form or ("H" in form and "O" not in form and len(form) > 2):
            continue                               # organometallics: not needed
        if lines[0][:18].split()[0] in BURCAT_EXCLUDE:
            continue
        text = " ".join(comment).upper()
        if any(tag in text for tag in BURCAT_REJECT):
            continue
        out.append("\n".join(comment + lines))
        n_b += 1
    head = ("! Extract of Burcat & Ruscic, Third Millennium Ideal Gas and Condensed Phase\n"
            "! Thermochemical Database (BURCAT.THR). Free for non-commercial use with\n"
            "! citation; commercial use requires the authors' written permission.\n"
            "! Species of Au, Pd, Pt, Sb and Bi (absent from NASA CEA); records unchanged,\n"
            "! comment blocks kept for provenance. Produced by tools/extract_trace_data.py.\n")
    (DATA / "trace_burcat.thr").write_text(head + "\n".join(out) + "\n")
    print(f"CEA: {len(kept)} species; Burcat: {n_b} species")


if __name__ == "__main__":
    main(*sys.argv[1:3])
