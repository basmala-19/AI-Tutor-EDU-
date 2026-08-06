# Google Colab

Open `AI_Tutor_Colab.ipynb` in Google Colab and run its cells sequentially.
It uses `benchmark.quality_benchmark`, not the older `benchmark/evaluator.py`.
The generated `after.csv` contains error tracebacks and parser-attempt details.
For every successfully parsed book it also writes:

- `benchmark/artifacts/json/<book>.json`: `EducationalDocument`, the input best suited to the Chunking stage.
- `benchmark/artifacts/markdown/<book>.md`: raw parser output for visual/debug review.
