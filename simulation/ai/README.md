# Using language models in PARAMANU (and where not to)

Language models are useful for **finding and organizing** data. They are not
evidence. A number becomes evidence only when a person has checked it
against the cited primary source and it enters the model through a data file
under version control (for example `paramanu_sim/data/trace_vapor.csv`).

## Good uses

1. **Data extraction.** Pull candidate values (boiling points, enthalpies of
   vaporization, activity coefficients of Au in liquid Fe, landfill element
   concentrations) from papers you supply, with the exact quote and page.
   `extract_parameters.py` does this against any OpenAI-compatible endpoint
   (vLLM, TGI, Ollama, or a hosted API) and writes a CSV marked
   `verified=no` for a human to check.
2. **Literature triage.** Rank papers on plasma vaporization, fractional
   condensation and landfill characterization for a human to read.
3. **Code review.** Ask a model to look for unit errors or sign mistakes in
   the solver, then confirm with the test suite.
4. **Surrogate models (future, GPU).** Train fast neural surrogates of the
   equilibrium solver to explore millions of feeds; every surrogate
   prediction used in the paper must be re-checked with the real solver.

## Not acceptable

* Values produced by a model without a verified primary source.
* "The model says it works" as an argument in the paper.

## Run the extractor

```bash
export PARAMANU_LLM_URL=http://your-server:8000/v1   # OpenAI-compatible
export PARAMANU_LLM_MODEL=your-model-name
export PARAMANU_LLM_KEY=...                           # if required
python extract_parameters.py paper.txt --ask "enthalpy of vaporization of gold at its boiling point"
```
