#!/usr/bin/env bash
# Build the PARAMANU paper in three formats from one LaTeX source.
#   output/PARAMANU_Reclaimer.pdf   pdfLaTeX (the master layout)
#   output/PARAMANU_Reclaimer.html  pdf2htmlEX render of the PDF (identical pages)
#   output/PARAMANU_Reclaimer.docx  pandoc + tools/reference.docx + Lua filters
#   output/PARAMANU_Reclaimer_blogger.html  one self-contained post for Blogger (MathJax, embedded figures)
# Needs: texlive (latex-extra, pictures, science), latexmk, poppler-utils,
#        pandoc >= 3, pdf2htmlEX. Regenerate the Word template with
#        tools/make_reference_docx.py (python-docx) only if styles change.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output

echo "== figures"
# figures produced by the simulation experiments (when the repository layout is present)
if [ -d ../simulation/results ]; then
  for f in fig_validation fig_ladder_simulated fig_ladder_recovery fig_reductant fig_sweep fig_fenske fig_reactor_design fig_sensitivity fig_alloy fig_breakdown fig_benchmarks fig_gold_copper; do
    cp ../simulation/results/$f.pdf ../simulation/results/$f.png figures/ 2>/dev/null || true
  done
fi
( cd figures
  for f in fig_atomize fig_ladder fig_energyenv fig_slider fig_process fig_chamber alg_batch; do
    pdflatex -interaction=nonstopmode -halt-on-error "$f.tex" > /dev/null
    pdftoppm -png -r 300 -singlefile "$f.pdf" "$f"          # PNG copies for Word
  done
  rm -f ./*.aux ./*.log )

echo "== PDF"
latexmk -pdf -interaction=nonstopmode -halt-on-error paramanu_paper.tex > /dev/null
mv paramanu_paper.pdf output/PARAMANU_Reclaimer.pdf   # move, not copy: one PDF on disk

echo "== HTML"
pdf2htmlEX --zoom 1.5 --embed-css 1 --embed-font 1 --embed-image 1 \
  --embed-javascript 1 --embed-outline 1 --process-outline 1 --bg-format svg \
  --dest-dir output output/PARAMANU_Reclaimer.pdf PARAMANU_Reclaimer.html > /dev/null 2>&1

echo "== Word"
# run from tools/ so pandoc does not expand paramanu.sty's LaTeX-only macros
( cd tools
  pandoc ../paramanu_paper.tex -f latex \
    --lua-filter docx-filter.lua --citeproc --lua-filter docx-post-filter.lua \
    --bibliography ../references.bib --csl paramanu-apalike.csl \
    --reference-doc reference.docx --resource-path=..:. \
    -o ../output/PARAMANU_Reclaimer.docx 2> >(grep -v "alg_batch_body" >&2)
  python3 docx_postprocess.py ../output/PARAMANU_Reclaimer.docx )

echo "== Blogger HTML"
# one self-contained post: MathJax for the formulas, figures embedded, scoped CSS
( cd tools
  pandoc ../paramanu_paper.tex -f latex \
    --lua-filter docx-filter.lua --citeproc --lua-filter docx-post-filter.lua \
    --bibliography ../references.bib --csl paramanu-apalike.csl --resource-path=..:. \
    -t html5 --mathjax -o ../output/.blogger_fragment.html 2> >(grep -v "alg_batch_body" >&2)
  python3 blogger_html.py ../output/.blogger_fragment.html ../output/PARAMANU_Reclaimer_blogger.html ..
  rm -f ../output/.blogger_fragment.html )

latexmk -c paramanu_paper.tex > /dev/null
echo "done:"; ls -la output/
