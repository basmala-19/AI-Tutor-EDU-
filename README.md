# Educational RAG Parsing Pipeline

This project converts Arabic, English, and mixed educational PDFs into a
structured `EducationalDocument` for an AI Tutor / RAG system.  It preserves
chapter, lesson, page, parser provenance, OCR confidence, tables, and images.

## Parser policy

The route is decided from the PDF contents, never from its filename:

| PDF type | Primary | Recovery |
|---|---|---|
| Born-digital (usable text layer) | Docling | LlamaParse, then Tesseract |
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

Tests use tiny generated PDF fixtures; no academic or benchmark PDFs are
committed. Ground truth must be human-reviewed before it is promoted and used
by the benchmark evaluator.
