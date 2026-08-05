"""Repeatable quality-only benchmark for real books without unverified GT."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from pipeline import run_pipeline


def run(input_dir: str, output_csv: str) -> None:
    pdfs = sorted(Path(input_dir).glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    rows = []
    for pdf in pdfs:
        try:
            result = run_pipeline(str(pdf))
            quality = result["quality_report"]
            rows.append({
                "file": pdf.name,
                "parser": result["parser"],
                "status": "PASS" if all(x["status"] == "PASS" for x in quality.values()) else "FAIL",
                **{name: value["detail"] for name, value in quality.items()},
            })
            print(f"[{rows[-1]['status']}] {pdf.name} ({result['parser']})")
        except Exception as exc:
            rows.append({"file": pdf.name, "parser": "-", "status": "ERROR", "error": str(exc)})
            print(f"[ERROR] {pdf.name}: {exc}")

    fieldnames = sorted({key for row in rows for key in row})
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quality benchmark for a directory of PDFs")
    parser.add_argument("input_dir", help="Directory containing the benchmark PDFs")
    parser.add_argument("--output", default="benchmark/reports/quality_benchmark.csv")
    args = parser.parse_args()
    run(args.input_dir, args.output)
