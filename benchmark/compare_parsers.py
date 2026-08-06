"""Run Docling and LiteParse on the same PDF and save an evidence-based comparison."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from educational.rule_based_parser import parse_markdown_to_education
from evaluation.reports import build_quality_report
from parsers.docling_parser import DoclingParser
from parsers.liteparse_parser import LiteParseParser
from routing.probe import probe_document
from routing.router import detect_language_from_content


def compare(file_path: str, output: str) -> list[dict]:
    probe = probe_document(file_path)
    language = detect_language_from_content(file_path)
    rows = []
    for parser in (LiteParseParser(), DoclingParser()):
        started = time.perf_counter()
        try:
            markdown = parser.parse(file_path)
            document = parse_markdown_to_education(markdown, file_path, parser.name, language)
            report = build_quality_report(markdown, document, probe.num_pages)
            rows.append({
                "parser": parser.name,
                "status": "PASS" if all(item["status"] == "PASS" for item in report.values()) else "FAIL",
                "seconds": round(time.perf_counter() - started, 3),
                "quality": report,
            })
        except Exception as exc:
            rows.append({"parser": parser.name, "status": "ERROR", "seconds": round(time.perf_counter() - started, 3), "error": f"{type(exc).__name__}: {exc}"})
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("file")
    cli.add_argument("--output", default="benchmark/reports/parser_comparison.json")
    args = cli.parse_args()
    print(json.dumps(compare(args.file, args.output), ensure_ascii=False, indent=2))
