"""
Ground Truth Extractor — high-performance structural metadata extraction from real PDFs.

Uses PyMuPDF (fitz) page analysis to extract:
  - Total page count
  - Image count
  - Table count
  - Estimated heading count
  - Born-digital status

Ground truth files are written to benchmark/ground_truth/<pdf_basename>.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import fitz

DEFAULT_TARGET_FILES = [
    r"C:\Users\CS\Downloads\Math_EN_prim1_Tr2.pdf",
    r"C:\Users\CS\Downloads\Math_AR_prp1_TR2.pdf",
    r"C:\Users\CS\Downloads\Math_AR_Prim1_T2.pdf",
    r"C:\Users\CS\Downloads\ICT_EN_prap1_TR2.pdf",
    r"C:\Users\CS\Downloads\Science_E_Prp1_TR2.pdf",
    r"C:\Users\CS\Downloads\ICT_En_Sec1_T1.pdf",
    r"C:\Users\CS\Downloads\ICT_Ar_Sec1_T1.pdf",
    r"C:\Users\CS\Downloads\History_Sec1_Tr1_2.pdf",
    r"C:\Users\CS\Downloads\pure_math_English_2s.pdf",
]


def extract_ground_truth(pdf_path: str, output_dir: str = "benchmark/ground_truth") -> dict:
    """Extract structural metadata from a PDF file and save as ground truth JSON.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Target directory for saving JSON ground truth.

    Returns:
        Dict containing ground truth metadata.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    total_images = 0
    total_tables = 0
    total_chars = 0

    for page in doc:
        total_images += len(page.get_images())
        text = page.get_text()
        total_chars += len(text)
        try:
            tabs = page.find_tables()
            if tabs and tabs.tables:
                total_tables += len(tabs.tables)
        except Exception:
            pass

    avg_chars = total_chars / max(total_pages, 1)
    is_born_digital = avg_chars >= 150
    estimated_headings = max(2, total_pages // 3)

    gt = {
        "file": os.path.basename(pdf_path),
        "num_pages": total_pages,
        "num_images": total_images,
        "num_tables": total_tables,
        "estimated_headings": estimated_headings,
        "is_born_digital": is_born_digital,
    }

    os.makedirs(output_dir, exist_ok=True)
    out_file = os.path.join(output_dir, Path(pdf_path).stem + ".json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)

    return gt


def generate_all_ground_truths(file_paths: list[str] | None = None) -> list[dict]:
    """Generate ground truth files for all target PDF paths.

    Args:
        file_paths: Optional list of PDF paths. Uses DEFAULT_TARGET_FILES if None.

    Returns:
        List of generated ground truth dictionaries.
    """
    paths = file_paths or DEFAULT_TARGET_FILES
    results = []
    print(f"Generating ground truth for {len(paths)} documents...")

    for path in paths:
        if not os.path.exists(path):
            print(f"Skipping missing file: {path}")
            continue
        gt = extract_ground_truth(path)
        results.append(gt)
        print(f"Extracted: {gt['file']} (pages={gt['num_pages']}, images={gt['num_images']}, tables={gt['num_tables']})")

    return results


if __name__ == "__main__":
    generate_all_ground_truths()
