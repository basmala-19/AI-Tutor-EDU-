"""
Quality report builder — aggregates all metrics into a single summary dict.

Separated from metrics.py so each function has a single responsibility:
  metrics.py  — individual metric logic
  reports.py  — orchestrates metrics into a report
"""
from __future__ import annotations

from schema.models import EducationalDocument
from evaluation.metrics import (
    content_faithfulness,
    metadata_completeness,
    reading_order,
    semantic_formatting,
    table_preservation,
)


def build_quality_report(
    source_markdown: str,
    edoc: EducationalDocument,
) -> dict[str, dict]:
    """Run all quality metrics and return a combined report.

    Args:
        source_markdown: Raw Markdown string from the parser.
        edoc:            Structured EducationalDocument after parsing.

    Returns:
        Dict mapping metric name → {"status": "PASS"|"FAIL", "detail": str}.
    """
    return {
        "content_faithfulness": content_faithfulness(source_markdown, edoc),
        "table_preservation": table_preservation(source_markdown, edoc),
        "semantic_formatting": semantic_formatting(edoc),
        "metadata_completeness": metadata_completeness(edoc),
        "reading_order": reading_order(edoc),
    }


def format_report(report: dict[str, dict], indent: int = 2) -> str:
    """Render a quality report as a human-readable string."""
    lines = []
    pad = " " * indent
    for metric, result in report.items():
        icon = "+" if result["status"] == "PASS" else "!"
        lines.append(f"{pad}[{icon}] {metric:<28} {result['detail']}")
    return "\n".join(lines)
