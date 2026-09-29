"""Shared figure style (matches the paper's palette) and result helpers."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"

COLORS = {"precious": "#C9A227", "bulk": "#1F4E9E", "toxic": "#C2185B",
          "light": "#2E8B2E", "refractory": "#7B3FA0", "other": "#707070"}
CLASS = {
    **{e: "precious" for e in ("Au", "Ag", "Pd", "Pt")},
    **{e: "toxic" for e in ("Hg", "Cd", "Pb", "Zn", "Sb", "Bi")},
    **{e: "refractory" for e in ("W", "Ti", "Nd")},
    **{e: "bulk" for e in ("Fe", "Al", "Cu", "Ni", "Co", "Sn", "Mn", "Cr", "Ga", "In", "Si", "Mg", "Ca")},
    **{e: "light" for e in ("H", "C", "N", "O", "F", "Cl", "S", "P", "Na", "K", "Li")},
}

# Use the paper's typeface (Latin Modern) when it is installed; fall back to DejaVu Serif.
_LM = Path("/usr/share/texmf/fonts/opentype/public/lm")
if _LM.exists():
    from matplotlib import font_manager

    for _f in ("lmroman10-regular.otf", "lmroman10-bold.otf", "lmroman10-italic.otf"):
        if (_LM / _f).exists():
            font_manager.fontManager.addfont(str(_LM / _f))
plt.rcParams.update({"font.family": "serif", "font.serif": ["Latin Modern Roman", "DejaVu Serif"],
                     "mathtext.fontset": "cm", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 150, "savefig.dpi": 300,
                     "savefig.bbox": "tight"})


def save(fig, name: str) -> None:
    RESULTS.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(RESULTS / f"{name}.{ext}")
    plt.close(fig)


def record(key: str, value) -> None:
    """Merge a headline number into results/key_numbers.json (used by the paper)."""
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / "key_numbers.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = value
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=float))
