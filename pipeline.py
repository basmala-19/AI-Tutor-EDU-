"""
Pipeline entry point.

Flow:
    PDF / Document
        |
        v
    Probe  (routing/probe.py)      — document fingerprinting
        |
        v
    Router (routing/router.py)     — content-based language detection & parser selection
        |
        v
    Parser (parsers/*.py)          — returns clean Markdown (Docling / Tesseract / LlamaParse fallback)
        |
        v
    Educational Parser             — Markdown → EducationalDocument (Pydantic)
    (educational/rule_based_parser.py)
        |
        v
    [Optional] Chunker             — EducationalDocument → list[chunk dict]
    (chunking/chunker.py)          — only when include_chunks=True

Usage:
    PYTHONPATH=. python pipeline.py sample_report.pdf
    PYTHONPATH=. python pipeline.py sample_report.pdf --chunks
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from routing.router import ParserRouter, detect_language_from_content
from educational.rule_based_parser import parse_markdown_to_education
from evaluation.reports import build_quality_report
from parsers.image_extractor import attach_extracted_images, extract_images_from_pdf


def run_pipeline(
    file_path: str,
    language: str | None = None,
    include_chunks: bool = False,
    include_markdown: bool = False,
    refine_with_qwen: bool = False,
    qwen_max_elements: int = 20,
) -> dict:
    """Run the full document pipeline.

    Args:
        file_path:      Path to the input document.
        language:       ISO language code when known ('en', 'ar'). Pass None to auto-detect
                        from actual document content.
        include_chunks: When True, also run the Chunking stage and include chunks
                        in the returned dict. When False (default), the pipeline
                        stops at EducationalDocument.

    Returns:
        Dict with keys: probe, parser, language, educational_document, quality_report,
        and optionally chunks / chunk_count, parser_markdown, and refinement_report.
    """
    if language is None:
        language = detect_language_from_content(file_path)

    router = ParserRouter()
    _, probe, detected_language = router.route(file_path)
    language = language or detected_language

    # The order depends on the actual PDF probe, not its file name. Digital
    # documents use Docling first; scans use local OCR first to avoid loading
    # Docling's layout models where there is no text layer to preserve.
    candidates = router.build_chain(probe, language)
    failures: list[str] = []
    parser_attempts: list[dict[str, str]] = []
    for selected_parser in candidates:
        try:
            markdown = selected_parser.parse(file_path)
            if markdown.strip():
                parser_attempts.append({"parser": selected_parser.name, "status": "success"})
                break
            detail = "returned empty output"
            failures.append(f"{selected_parser.name}: {detail}")
            parser_attempts.append({"parser": selected_parser.name, "status": "failed", "detail": detail})
        except Exception as exc:
            detail = str(exc)
            failures.append(f"{selected_parser.name}: {detail}")
            parser_attempts.append({"parser": selected_parser.name, "status": "failed", "detail": detail})
    else:
        raise RuntimeError("All parsers failed. " + " | ".join(failures))

    edoc = parse_markdown_to_education(
        markdown_text=markdown,
        source_file=file_path,
        parser=selected_parser.name,
        language=language,
    )

    images_by_page = extract_images_from_pdf(file_path)
    attach_extracted_images(edoc, images_by_page, parser=selected_parser.name)

    refinement_report = None
    if refine_with_qwen:
        from educational.llm_parser import QwenVLRefiner
        refinement_report = QwenVLRefiner().refine(edoc, file_path, qwen_max_elements)

    quality_report = build_quality_report(markdown, edoc, expected_page_count=probe.num_pages)

    result: dict = {
        "probe": asdict(probe),
        "parser": selected_parser.name,
        "parser_attempts": parser_attempts,
        "language": language,
        "educational_document": json.loads(edoc.model_dump_json(exclude_none=True)),
        "quality_report": quality_report,
    }
    if hasattr(selected_parser, "last_page_markers"):
        result["page_markers"] = selected_parser.last_page_markers
    if refinement_report is not None:
        result["refinement_report"] = refinement_report

    if include_chunks:
        from chunking.chunker import chunk_educational_document
        chunks = chunk_educational_document(edoc)
        result["chunks"] = chunks
        result["chunk_count"] = len(chunks)

    if include_markdown:
        result["parser_markdown"] = markdown

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG document pipeline")
    parser.add_argument("file", nargs="?", default="test_docs/academic.pdf")
    parser.add_argument(
        "--chunks",
        action="store_true",
        help="Also run the Chunking stage (default: off)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="ISO language code, e.g. 'en' or 'ar' (default: auto content-based detection)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    res = run_pipeline(args.file, language=args.language, include_chunks=args.chunks)

    print(f"Parser      : {res['parser']}")
    for attempt in res["parser_attempts"]:
        suffix = f" ({attempt['detail']})" if "detail" in attempt else ""
        print(f"  - {attempt['parser']}: {attempt['status']}{suffix}")
    print(f"Language    : {res['language']}")
    print(f"Chapters    : {len(res['educational_document']['chapters'])}")
    if "page_markers" in res:
        markers = res["page_markers"]
        preview = markers if len(markers) <= 20 else markers[:10] + ["..."] + markers[-3:]
        print(f"Page markers: {preview}")
    print("Quality     :")
    for metric, val in res["quality_report"].items():
        icon = "+" if val["status"] == "PASS" else "!"
        print(f"  [{icon}] {metric:<28} {val['detail']}")
