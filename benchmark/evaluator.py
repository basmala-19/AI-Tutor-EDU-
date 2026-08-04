"""
EducationalParseBench Evaluator — evaluates full pipeline performance against Official Ground Truth.

Pipeline Benchmark Architecture:
    PDF Document
        ↓
    generate_reference.py  (candidate structure -> benchmark/reference/)
        ↓
    review_reference.py    (validation & promotion -> benchmark/ground_truth/)
        ↓
    evaluator.py           (evaluates pipeline against official Ground Truth)

Outputs:
  - JSON Report:      benchmark/reports/benchmark_report.json
  - HTML Dashboard:   benchmark/reports/benchmark.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import fitz

# Support both ``python -m benchmark.evaluator`` and the more convenient
# ``python benchmark/evaluator.py`` from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parsers.base import BaseParser
from parsers.docling_parser import DoclingParser
from routing.router import ParserRouter
from educational.rule_based_parser import parse_markdown_to_education
from evaluation.reports import build_quality_report
from benchmark.generate_reference import ALL_TARGET_FILES, generate_all_references
from benchmark.review_reference import review_and_promote


MIN_CHAPTER_RECALL = 0.50
MIN_LESSON_RECALL = 0.50
MIN_TABLE_RECALL = 0.50


class PyMuPDFFallbackParser(BaseParser):
    """Fast offline fallback parser using PyMuPDF layout extraction."""

    name = "pymupdf_fallback"

    def parse(self, file_path: str) -> str:
        doc = fitz.open(file_path)
        markdown_blocks = []

        for page in doc:
            page_num = page.number + 1
            blocks = page.get_text("blocks")
            for b in blocks:
                if b[6] == 0:  # text block
                    text = b[4].strip()
                    if not text:
                        continue
                    first_line = text.split("\n")[0].strip()
                    if len(first_line) < 60 and (
                        first_line.lower().startswith(("chapter", "unit", "lesson")) or
                        first_line.startswith(("الفصل", "الدرس", "الوحدة"))
                    ):
                        markdown_blocks.append(f"# {first_line}\n")
                    else:
                        markdown_blocks.append(f"{text}\n")

            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for tab in tabs.tables:
                        markdown_blocks.append("\n" + "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in tab.extract()) + "\n")
            except Exception:
                pass

        return "\n\n".join(markdown_blocks)


def run_pipeline_with_fallback(file_path: str, use_primary_parser: bool = False) -> dict:
    """Run pipeline with graceful fallback for unconfigured external APIs / OCR backends.

    Args:
        file_path: Path to the input PDF file.

    Returns:
        Pipeline execution result dictionary.
    """
    router = ParserRouter()
    # ParserRouter.route() is the single routing contract.  It returns the
    # parser, probe result, and content-derived language in that order.
    # Keeping all three values here prevents this standalone benchmark path
    # from drifting away from pipeline.run_pipeline().
    selected_parser, probe, language = router.route(file_path)

    if use_primary_parser:
        try:
            markdown = selected_parser.parse(file_path)
            parser_used = selected_parser.name
        except Exception:
            fallback_parser = PyMuPDFFallbackParser()
            markdown = fallback_parser.parse(file_path)
            parser_used = f"{selected_parser.name}_fallback({fallback_parser.name})"
    else:
        # Docling downloads a ~1 GB model on first use.  The benchmark should
        # remain runnable and deterministic without a network/model setup.
        fallback_parser = PyMuPDFFallbackParser()
        markdown = fallback_parser.parse(file_path)
        parser_used = fallback_parser.name

    edoc = parse_markdown_to_education(
        markdown_text=markdown,
        source_file=file_path,
        parser=parser_used,
        language=language,
    )

    quality_report = build_quality_report(markdown, edoc)

    return {
        "probe": probe,
        "parser": parser_used,
        "educational_document": json.loads(edoc.model_dump_json(exclude_none=True)),
        "quality_report": quality_report,
    }


def evaluate_document_vs_gt(
    pdf_path: str,
    gt_dir: str = "benchmark/ground_truth",
    use_primary_parser: bool = False,
) -> dict:
    """Evaluate pipeline performance on a single document against its official Ground Truth JSON.

    Args:
        pdf_path: Path to the input PDF document.
        gt_dir: Directory containing official Ground Truth JSON files.

    Returns:
        Evaluation dictionary with granular recall metrics and quality report.
    """
    stem = Path(pdf_path).stem
    gt_path = os.path.join(gt_dir, f"{stem}.json")

    if not os.path.exists(gt_path):
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    with open(gt_path, "r", encoding="utf-8") as f:
        gt = json.load(f)

    review = gt.get("human_review", {})
    if (
        gt.get("status") != "HUMAN_VERIFIED_GROUND_TRUTH"
        or not review.get("approved_by")
        or not review.get("approved_at")
        or not gt.get("source_sha256")
        or any(status != "passed" for status in gt.get("review_checklist", {}).values())
    ):
        raise ValueError(
            "Ground truth is not human-verified. Llama-generated references "
            "must remain candidates until a reviewer records approved_by and approved_at."
        )

    # Execute pipeline with fallback support
    result = run_pipeline_with_fallback(pdf_path, use_primary_parser=use_primary_parser)
    edoc = result["educational_document"]
    quality = result["quality_report"]

    # Ground Truth structural counts
    gt_chapters = [ch["title"].lower().strip() for ch in gt.get("chapters", [])]
    gt_lessons = [le["title"].lower().strip() for ch in gt.get("chapters", []) for le in ch.get("lessons", [])]
    gt_tables = sum(
        1 for ch in gt.get("chapters", []) for le in ch.get("lessons", []) for el in le.get("elements", []) if el.get("type") == "table"
    )

    # Pipeline output structural counts
    parsed_chapters = [ch["title"].lower().strip() for ch in edoc.get("chapters", [])]
    parsed_lessons = [le["title"].lower().strip() for ch in edoc.get("chapters", []) for le in ch.get("lessons", [])]
    parsed_tables = sum(
        1 for ch in edoc.get("chapters", []) for le in ch.get("lessons", []) for el in le.get("elements", []) if el.get("type") == "table"
    )

    # Calculate structural recall
    found_chapters = sum(1 for ch in gt_chapters if any(ch in p or p in ch for p in parsed_chapters))
    chapter_recall = round(found_chapters / max(len(gt_chapters), 1), 3)

    found_lessons = sum(1 for le in gt_lessons if any(le in p or p in le for p in parsed_lessons))
    lesson_recall = round(found_lessons / max(len(gt_lessons), 1), 3)

    table_recall = round(min(parsed_tables / gt_tables, 1.0), 3) if gt_tables > 0 else 1.0

    quality_pass = all(metric.get("status") == "PASS" for metric in quality.values())
    # A parser that preserves its own (empty or incomplete) Markdown can pass
    # local quality checks while recovering none of the ground-truth structure.
    # Benchmark status must therefore include the ground-truth comparison.
    structure_pass = (
        chapter_recall >= MIN_CHAPTER_RECALL
        and lesson_recall >= MIN_LESSON_RECALL
        and table_recall >= MIN_TABLE_RECALL
    )
    status = "PASS" if quality_pass and structure_pass else "FAIL"

    return {
        "file": os.path.basename(pdf_path),
        "parser": result["parser"],
        "status": status,
        "quality_status": "PASS" if quality_pass else "FAIL",
        "structure_status": "PASS" if structure_pass else "FAIL",
        "num_pages": gt.get("num_pages", 0),
        "chapter_recall": chapter_recall,
        "lesson_recall": lesson_recall,
        "table_recall": table_recall,
        "gt_chapters_count": len(gt_chapters),
        "parsed_chapters_count": len(parsed_chapters),
        "gt_lessons_count": len(gt_lessons),
        "parsed_lessons_count": len(parsed_lessons),
        "gt_tables_count": gt_tables,
        "parsed_tables_count": parsed_tables,
        "quality_report": quality,
    }


def generate_html_dashboard(summary: dict, output_path: str = "benchmark/reports/benchmark.html") -> None:
    """Generate a clean HTML Dashboard for visualizing benchmark evaluation results."""
    evals_rows = []
    for ev in summary.get("evaluations", []):
        badge = '<span style="background: #22c55e; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">PASS</span>' if ev["status"] == "PASS" else '<span style="background: #ef4444; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">FAIL</span>'
        evals_rows.append(f"""
        <tr>
            <td><strong>{ev['file']}</strong></td>
            <td><code>{ev['parser']}</code></td>
            <td>{ev['num_pages']}</td>
            <td>{badge}</td>
            <td>{ev['chapter_recall']:.0%}</td>
            <td>{ev['lesson_recall']:.0%}</td>
            <td>{ev['table_recall']:.0%}</td>
        </tr>
        """)

    table_body = "\n".join(evals_rows)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EducationalParseBench Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 30px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; font-size: 28px; margin-bottom: 5px; }}
        p.subtitle {{ color: #94a3b8; font-size: 14px; margin-top: 0; margin-bottom: 30px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; }}
        .card .title {{ font-size: 12px; text-transform: uppercase; color: #94a3b8; letter-spacing: 1px; }}
        .card .val {{ font-size: 32px; font-weight: bold; color: #38bdf8; margin-top: 8px; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; border: 1px solid #334155; }}
        th {{ background: #334155; padding: 12px 16px; text-align: left; font-size: 13px; color: #cbd5e1; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #334155; font-size: 14px; color: #e2e8f0; }}
        tr:hover {{ background: #0f172a; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>EducationalParseBench Dashboard</h1>
        <p class="subtitle">Document Parsing & Structural Quality Assessment Report</p>

        <div class="grid">
            <div class="card">
                <div class="title">Total Documents</div>
                <div class="val">{summary['total_documents']}</div>
            </div>
            <div class="card">
                <div class="title">Pass Rate</div>
                <div class="val">{summary['pass_rate']:.0%}</div>
            </div>
            <div class="card">
                <div class="title">Avg Chapter Recall</div>
                <div class="val">{summary['avg_chapter_recall']:.0%}</div>
            </div>
            <div class="card">
                <div class="title">Avg Table Recall</div>
                <div class="val">{summary['avg_table_recall']:.0%}</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Document</th>
                    <th>Parser</th>
                    <th>Pages</th>
                    <th>Status</th>
                    <th>Chapter Recall</th>
                    <th>Lesson Recall</th>
                    <th>Table Recall</th>
                </tr>
            </thead>
            <tbody>
                {table_body}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def run_benchmark(
    target_files: list[str] | None = None,
    report_json: str = "benchmark/reports/benchmark_report.json",
    report_html: str = "benchmark/reports/benchmark.html",
    refresh_references: bool = False,
    use_primary_parser: bool = False,
) -> dict:
    """Evaluate the pipeline against existing official Ground Truth.

    Set ``refresh_references`` only when intentionally rebuilding the
    candidate references.  Normal evaluation stays offline and never masks
    an API upload failure by evaluating stale files.
    """
    files = target_files or ALL_TARGET_FILES
    gt_dir = "benchmark/ground_truth"

    if refresh_references:
        print("Stage 1/3: Generating Candidate Reference Structures...")
        generate_all_references(files)
        print("Stage 2/3: Validating & Promoting to Official Ground Truth...")
        review_and_promote()
    else:
        print("Using existing official Ground Truth (reference refresh disabled).")

    print("Evaluating Pipeline against Official Ground Truth...")
    evaluations = []
    passed_count = 0

    print("\n" + "=" * 80)
    print(f"EDUCATIONAL PARSEBENCH EVALUATION ({len(files)} DOCUMENTS)")
    print("=" * 80)

    for pdf_path in files:
        if not os.path.exists(pdf_path):
            print(f"[SKIP] File not found: {pdf_path}")
            continue

        try:
            res = evaluate_document_vs_gt(
                pdf_path,
                gt_dir=gt_dir,
                use_primary_parser=use_primary_parser,
            )
            evaluations.append(res)
            if res["status"] == "PASS":
                passed_count += 1

            print(
                f"[{res['status']}] {res['file']:<36} "
                f"parser={res['parser']:<30} "
                f"ch_recall={res['chapter_recall']:.2f} "
                f"le_recall={res['lesson_recall']:.2f} "
                f"tbl_recall={res['table_recall']:.2f}"
            )
        except Exception as exc:
            print(f"[FAIL] {os.path.basename(pdf_path)}: {exc}")

    avg_ch_recall = round(sum(e["chapter_recall"] for e in evaluations) / max(len(evaluations), 1), 3)
    avg_le_recall = round(sum(e["lesson_recall"] for e in evaluations) / max(len(evaluations), 1), 3)
    avg_tbl_recall = round(sum(e["table_recall"] for e in evaluations) / max(len(evaluations), 1), 3)

    summary = {
        "total_documents": len(evaluations),
        "passed_documents": passed_count,
        "pass_rate": round(passed_count / max(len(evaluations), 1), 3),
        "avg_chapter_recall": avg_ch_recall,
        "avg_lesson_recall": avg_le_recall,
        "avg_table_recall": avg_tbl_recall,
        "evaluations": evaluations,
    }

    os.makedirs(os.path.dirname(report_json), exist_ok=True)
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    generate_html_dashboard(summary, output_path=report_html)

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY REPORT")
    print("=" * 80)
    print(f"Total Documents    : {summary['total_documents']}")
    print(f"Passed Documents   : {summary['passed_documents']}/{summary['total_documents']} ({summary['pass_rate']:.0%})")
    print(f"Avg Chapter Recall : {summary['avg_chapter_recall']:.3f}")
    print(f"Avg Lesson Recall  : {summary['avg_lesson_recall']:.3f}")
    print(f"Avg Table Recall   : {summary['avg_table_recall']:.3f}")
    print(f"JSON Report        : {report_json}")
    print(f"HTML Dashboard     : {report_html}")
    print("=" * 80)

    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EducationalParseBench Evaluator")
    parser.add_argument("--json", default="benchmark/reports/benchmark_report.json", help="Path for JSON report")
    parser.add_argument("--html", default="benchmark/reports/benchmark.html", help="Path for HTML dashboard")
    parser.add_argument(
        "--refresh-references",
        action="store_true",
        help="Regenerate candidate references and promote them before evaluation (requires LlamaCloud).",
    )
    parser.add_argument(
        "--use-primary-parser",
        action="store_true",
        help="Use the router-selected parser (Docling/OCR); otherwise use fast offline PyMuPDF parsing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary_report = run_benchmark(
        report_json=args.json,
        report_html=args.html,
        refresh_references=args.refresh_references,
        use_primary_parser=args.use_primary_parser,
    )
    sys.exit(0)
