"""Quality benchmark must retain failures as actionable evidence."""

import csv

from benchmark import quality_benchmark


def test_runner_writes_error_and_traceback_for_failed_document(tmp_path, monkeypatch):
    (tmp_path / "broken.pdf").write_bytes(b"not a PDF")

    def fail(_: str):
        raise ValueError("intentional parser failure")

    monkeypatch.setattr(quality_benchmark, "run_pipeline", fail)
    output = tmp_path / "result.csv"
    quality_benchmark.run(str(tmp_path), str(output))

    with output.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["status"] == "ERROR"
    assert row["error"] == "ValueError: intentional parser failure"
    assert "ValueError: intentional parser failure" in row["traceback"]


def test_runner_records_parser_attempts(tmp_path, monkeypatch):
    (tmp_path / "book.pdf").write_bytes(b"placeholder")
    monkeypatch.setattr(
        quality_benchmark,
        "run_pipeline",
        lambda _: {
            "parser": "tesseract",
            "parser_attempts": [{"parser": "docling", "status": "failed", "detail": "bad layout"}],
            "quality_report": {"content": {"status": "PASS", "detail": "ok"}},
        },
    )
    output = tmp_path / "result.csv"
    quality_benchmark.run(str(tmp_path), str(output))
    with output.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert "bad layout" in row["parser_attempts"]
