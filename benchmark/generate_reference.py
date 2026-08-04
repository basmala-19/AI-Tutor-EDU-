"""
Reference Generator — generates authentic EducationalDocument structure from real PDFs.

Uses LlamaParser (LlamaCloud REST API) to extract real Markdown, then runs the
rule-based Educational Parser to produce the structured JSON reference.

Output schema matches EducationalDocument:
    {
        "source_file": "<filename>",
        "language": "<auto|en|ar>",
        "chapters": [
            {
                "title": "<Chapter Title>",
                "lessons": [
                    {
                        "title": "<Lesson Title>",
                        "elements": [
                            {"type": "heading|paragraph|table|image", "text": "...", "level": 1}
                        ]
                    }
                ]
            }
        ]
    }

Files are saved to benchmark/reference/<filename>.json for human review.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ALL_TARGET_FILES = [
    r"C:\Users\CS\Downloads\Math_EN_prim1_Tr2.pdf",
    r"C:\Users\CS\Downloads\Math_AR_prp1_TR2.pdf",
    r"C:\Users\CS\Downloads\Math_AR_Prim1_T2.pdf",
    r"C:\Users\CS\Downloads\ICT_EN_prap1_TR2.pdf",
    r"C:\Users\CS\Downloads\Science_E_Prp1_TR2.pdf",
    r"C:\Users\CS\Downloads\ICT_En_Sec1_T1.pdf",
    r"C:\Users\CS\Downloads\ICT_Ar_Sec1_T1.pdf",
    r"C:\Users\CS\Downloads\History_Sec1_Tr1_2.pdf",
    r"C:\Users\CS\Downloads\pure_math_English_2s.pdf",
    r"C:\Users\CS\Downloads\integrated_science_EN_1_Secondary_TR2.pdf",
    r"C:\Users\CS\Downloads\Biology_ARABIC_Sec3.pdf",
]


def generate_reference_json(pdf_path: str, output_dir: str = "benchmark/reference") -> dict:
    """Generate structured reference JSON from a real PDF using LlamaParser + Educational Parser.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory to save generated reference JSON.

    Returns:
        Structured reference dictionary.
    """
    from parsers.llama_parser import LlamaParser
    from educational.rule_based_parser import parse_markdown_to_education
    from routing.router import detect_language_from_content

    filename = os.path.basename(pdf_path)

    # Step 1: Parse the PDF via LlamaCloud to get real Markdown
    language = detect_language_from_content(pdf_path)
    # Language is derived from the PDF text layer, never from the filename.
    parser = LlamaParser(language=language if language in {"ar", "en"} else "auto")
    markdown = parser.parse(pdf_path)

    # Step 2: Run Educational Parser to get structured document
    edoc = parse_markdown_to_education(
        markdown_text=markdown,
        source_file=filename,
        parser="llamaparse",
        language=language,
    )

    # Step 3: Serialize to reference JSON format
    ref_doc = json.loads(edoc.model_dump_json(exclude_none=True))
    ref_doc["markdown_length"] = len(markdown)
    ref_doc["reference_kind"] = "LLAMA_GENERATED_CANDIDATE"

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, Path(pdf_path).stem + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ref_doc, f, indent=2, ensure_ascii=False)

    return ref_doc


def generate_all_references(file_paths: list[str] | None = None) -> list[dict]:
    """Generate reference JSON files for all target PDF documents using LlamaParser."""
    paths = file_paths or ALL_TARGET_FILES
    results = []
    print(f"Generating real reference structures for {len(paths)} documents via LlamaCloud...")

    for path in paths:
        if not os.path.exists(path):
            print(f"Skipping missing file: {path}")
            continue
        try:
            ref = generate_reference_json(path)
            results.append(ref)
            ch_count = len(ref.get("chapters", []))
            md_len = ref.get("markdown_length", 0)
            print(f"Generated: {os.path.basename(path)} ({ch_count} chapters, {md_len} chars)")
        except Exception as exc:
            print(f"Failed: {os.path.basename(path)}: {exc}")

    return results


if __name__ == "__main__":
    generate_all_references()
