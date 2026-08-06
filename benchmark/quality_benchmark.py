"""Repeatable quality-only benchmark for real books without unverified GT."""
from __future__ import annotations

import argparse
import csv
import json
import traceback
from pathlib import Path

from pipeline import run_pipeline


def run(
    input_dir: str,
    output_csv: str,
    files: list[str] | None = None,
    artifacts_dir: str | None = None,
) -> None:
    pdfs = [Path(path) for path in files] if files else sorted(Path(input_dir).glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    rows = []
    artifacts = Path(artifacts_dir) if artifacts_dir else None
    if artifacts:
        (artifacts / "json").mkdir(parents=True, exist_ok=True)
        (artifacts / "markdown").mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        try:
            result = run_pipeline(str(pdf), include_markdown=artifacts is not None)
            quality = result["quality_report"]
            if artifacts:
                stem = pdf.stem
                with (artifacts / "json" / f"{stem}.json").open("w", encoding="utf-8") as handle:
                    json.dump(result["educational_document"], handle, ensure_ascii=False, indent=2)
                with (artifacts / "markdown" / f"{stem}.md").open("w", encoding="utf-8") as handle:
                    handle.write(result["parser_markdown"])
            rows.append({
                "file": pdf.name,
                "parser": result["parser"],
                "status": "PASS" if all(x["status"] == "PASS" for x in quality.values()) else "FAIL",
                "parser_attempts": json.dumps(result.get("parser_attempts", []), ensure_ascii=False),
                **{name: value["detail"] for name, value in quality.items()},
            })
            print(f"[{rows[-1]['status']}] {pdf.name} ({result['parser']})")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            rows.append(
                {
                    "file": pdf.name,
                    "parser": "-",
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": details,
                }
            )
            print(f"[ERROR] {pdf.name}: {rows[-1]['error']}")

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
    parser.add_argument("--files", nargs="+", help="Optional explicit PDF paths for an isolated rerun")
    parser.add_argument(
        "--artifacts-dir",
        help="Write one EducationalDocument JSON and raw Markdown file per successful PDF",
    )
    args = parser.parse_args()
    run(args.input_dir, args.output, args.files, args.artifacts_dir)
