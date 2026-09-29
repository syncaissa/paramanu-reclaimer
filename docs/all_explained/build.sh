#!/usr/bin/env bash
# Build AllExplainedHere.pdf, the detailed companion to the paper.
# The PDF is written to the directory given as $1 (default: the repository root);
# build products are removed so only the one PDF remains.
set -euo pipefail
OUT="$(cd "${1:-$(dirname "$0")/../..}" && pwd)"    # resolved before changing directory
cd "$(dirname "$0")"
"${PYTHON:-python3}" -W ignore make_tables.py > /dev/null     # data tables from simulation/results
export TEXINPUTS=".:../../paper:"
export BIBINPUTS=".:../../paper:"
latexmk -pdf -interaction=nonstopmode -halt-on-error AllExplainedHere.tex > build.log 2>&1 || { tail -40 build.log; exit 1; }
mv AllExplainedHere.pdf "$OUT/AllExplainedHere.pdf"
latexmk -C AllExplainedHere.tex > /dev/null 2>&1 || true
rm -rf AllExplainedHere.bbl build.log tables
echo "wrote $OUT/AllExplainedHere.pdf"
