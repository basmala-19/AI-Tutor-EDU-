# Educational RAG Parsing Pipeline

This project converts Arabic, English, and mixed educational PDFs into a
structured `EducationalDocument` for an AI Tutor / RAG system.  It preserves
chapter, lesson, page, parser provenance, OCR confidence, tables, and images.

## Parser policy

The route is decided from the PDF contents, never from its filename:

| PDF type | Primary | Recovery |
|---|---|---|
| Born-digital (usable text layer) | LiteParse | Docling, LlamaParse, then Tesseract |
| Scanned / image-only | Tesseract (`ara`, `eng`, or both) | LlamaParse |

`TesseractParser` writes an OCR confidence per page. Elements below 60% are
tagged `metadata.extra.needs_review = true`; the quality report exposes this
as `ocr_confidence`.

## Local setup (Windows)

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "."
python pipeline.py "C:\path\to\book.pdf" --chunks
python -m pytest -q
```

Install Tesseract from the UB Mannheim build, and ensure `ara` and `eng` are
listed by `tesseract --list-langs`. The parser also detects the usual Windows
installation path automatically.

To enable LlamaParse recovery, create a local `.env` file (never commit it):

```text
LLAMA_CLOUD_API_KEY=your_key_here
```

## Google Colab

Clone your GitHub repository, then run these cells:

```python
!git clone https://github.com/YOUR_USER/YOUR_REPOSITORY.git
%cd YOUR_REPOSITORY
!apt-get -qq update && apt-get -qq install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
!pip -q install -r requirements-colab.txt
```

Optional, only if LlamaParse fallback is needed:

```python
import os
os.environ["LLAMA_CLOUD_API_KEY"] = "your_key_here"
```

Upload a PDF with the Colab file picker, then run:

```python
from pipeline import run_pipeline

result = run_pipeline("/content/book.pdf", include_chunks=True)
print(result["parser"], result["language"], result["quality_report"])
```

## Testing

```powershell
$env:PYTHONPATH = "."
python -m pytest -q
```

## Local Parse Studio

Launch a LlamaParse-style local review interface (PDF page beside synchronized
Markdown and JSON) without a cloud API:

```powershell
$env:PYTHONPATH = "."
streamlit run app.py
```

The JSON download is the structured `EducationalDocument` to use in the next
Chunking stage; Markdown is retained for parser review and debugging.

LiteParse exposes page-scoped text to the viewer, so its Markdown panel stays
synchronised with the selected PDF page even when its combined Markdown export
does not include explicit page markers.

## Optional PaddleOCR recovery for weak scans

Tesseract remains the default OCR engine.  If PaddleOCR is installed, it is
loaded only for pages below 60% Tesseract confidence and its text replaces the
page only when Paddle's confidence is higher.  This avoids a second OCR pass on
every page of every book.

```powershell
# First install PaddlePaddle for your CPU/CUDA version from its official guide.
python -m pip install -r requirements-paddle.txt
```

## Persistent Streamlit deployment

Colab and Kaggle are temporary notebook sessions; they cannot keep Streamlit
running permanently.  This repository includes a Docker image for a persistent
host (for example a VM, Render, Railway, or Hugging Face Space):

```powershell
docker build -t ai-tutor-parse-studio .
docker run --rm -p 8501:8501 ai-tutor-parse-studio
```

Open `http://localhost:8501`.  A free hosted tier may sleep when idle; an
always-on deployment requires a host/plan that does not sleep.

### Compare local parsers

Measure LiteParse and Docling on the same PDF before promoting either parser:

```powershell
$env:PYTHONPATH = "."
python -m benchmark.compare_parsers "C:\path\to\book.pdf"
```

The comparison writes parser time and all quality metrics to
`benchmark/reports/parser_comparison.json`.

### Optional local Qwen-VL refinement

Qwen is an opt-in post-processing layer, not a replacement parser. It only
reviews images without useful captions, tables without rows, invalid headings,
and low-confidence OCR. It preserves existing text and records every accepted
change in `metadata.extra.refined_by = "qwen"`.

```powershell
python -m pip install -r requirements-qwen.txt
streamlit run app.py
```

Use a GPU runtime (for example, Colab GPU) and enable **Refine flagged elements
with local Qwen-VL** in the sidebar. The default model, Qwen2.5-VL-3B, downloads
on first use. It can improve visual descriptions but is not guaranteed to match
LlamaParse; validate its `refinement_report` and the quality metrics per book.

Parse Studio requires only a PDF upload. It decides automatically: image-dense
born-digital books use Qwen-VL per page, and regular text books use
Docling/Tesseract. It always prepares chunks for the next RAG stage. Qwen is
loaded in 4-bit mode on CUDA and, if it cannot run (for example VRAM is
unavailable), the pipeline records the failed Qwen attempt then falls back to
Docling/Tesseract. It is significantly slower, and fidelity must be measured
against your LlamaParse reference rather than assumed.

Tests use tiny generated PDF fixtures; no academic or benchmark PDFs are
committed. Ground truth must be human-reviewed before it is promoted and used
by the benchmark evaluator.
