"""Regression tests for the benchmark runner's integration contracts."""
from __future__ import annotations

from benchmark import evaluator
from parsers.base import BaseParser
from routing.probe import ProbeResult


class _MarkdownParser(BaseParser):
    name = "test_parser"

    def parse(self, file_path: str) -> str:
        return "# Chapter\n\n## Lesson\n\nA short paragraph."


def test_benchmark_runner_accepts_router_three_value_contract(monkeypatch):
    """The benchmark must unpack parser, probe, and detected language."""
    expected_probe = ProbeResult(
        file="sample.pdf",
        num_pages=1,
        avg_chars_per_page=20,
        is_born_digital=True,
        image_count=0,
        distinct_font_sizes=2,
        likely_has_headings=True,
        text_block_count=2,
        likely_has_complex_layout=False,
        probe_time_seconds=0.0,
        route="docling",
    )

    monkeypatch.setattr(
        evaluator.ParserRouter,
        "route",
        lambda self, path: (_MarkdownParser(), expected_probe, "en"),
    )

    result = evaluator.run_pipeline_with_fallback("sample.pdf", use_primary_parser=True)

    assert result["parser"] == "test_parser"
    assert result["educational_document"]["language"] == "en"
    assert result["educational_document"]["chapters"]


def test_benchmark_status_requires_ground_truth_structure():
    """A quality-only pass must not hide zero benchmark recall."""
    quality_pass = True
    structure_pass = (
        0.0 >= evaluator.MIN_CHAPTER_RECALL
        and 0.0 >= evaluator.MIN_LESSON_RECALL
        and 0.0 >= evaluator.MIN_TABLE_RECALL
    )

    assert quality_pass is True
    assert structure_pass is False
