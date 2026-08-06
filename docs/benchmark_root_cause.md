# Benchmark root-cause notes

Baseline: `benchmark_results.csv`, supplied from the real 11-book run.

## Reading order (under investigation)

An earlier hypothesis identified image insertion as one possible source of a
high-to-low transition, and `attach_extracted_images` now inserts visuals in
page order. The newer 11-file CSV still reports Docling-only regressions such
as `48 -> 7`, `51 -> 6`, and `187 -> 4`; therefore image insertion was not a
sufficient root cause. No further reading-order fix should be claimed until
the page marker stream and raw Docling Markdown are captured for a failing
file. `DoclingParser.last_page_markers` exposes the marker sequence, and the
CLI prints it for a Docling run.

Docling 2.118.0's Markdown export does not attach per-element page provenance.
The pipeline now converts one source page at a time, emitting exact markers
`1, 2, ... N`, instead of one approximate marker per ten-page batch. This is
slower but makes page coverage and reading-order checks meaningful.

## Tables

Installed Docling: `2.118.0`. Inspection showed its default
`table_structure_options.mode` is already `TableFormerMode.ACCURATE`; the
baseline loss cannot be attributed to an accidental FAST default. The parser
now pins ACCURATE explicitly and retains both raw Markdown and additive parsed
`rows` for clean pipe tables. OCR-only table recognition remains a separate
experiment; it must be compared on matched pages before any architecture
change.

## Math_EN anomaly

The baseline row contains no parser result or error (`parser=-`, `status=FAIL`),
unlike the other rows. It is therefore an execution anomaly, not evidence of a
shared Arabic-OCR or table bug. Re-run it alone with:

```powershell
$env:PYTHONPATH='.'
python pipeline.py 'C:\Users\CS\Downloads\Math_EN_prim1_Tr2.pdf'
```

Keep the raw Markdown/exception from that isolated run before proposing a
file-specific fix.

## Re-running the quality comparison

The old JSON ground truth is intentionally rejected unless human-reviewed.
For a valid before/after quality comparison of the same 11 PDFs:

```powershell
$env:PYTHONPATH='.'
python -m benchmark.quality_benchmark 'C:\Users\CS\Downloads' --output benchmark/reports/after.csv
```

Compare `after.csv` with the supplied `benchmark_results.csv`. This does not
claim structural recall against Llama-generated references; it reports only
pipeline quality on the same source files.
