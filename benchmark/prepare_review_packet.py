"""Create a human-review packet from a LlamaParse reference candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_review_packet(pdf_path: str, reference_dir: str = "benchmark/reference") -> Path:
    """Copy a parser candidate into the reviewed queue with a required checklist.

    A reviewer must correct the document structure against the PDF and fill in
    ``human_review`` before ``review_reference.py`` will promote it.
    """
    pdf = Path(pdf_path)
    candidate_path = Path(reference_dir) / f"{pdf.stem}.json"
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate not found: {candidate_path}")

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate.update(
        {
            "status": "REVIEW_REQUIRED",
            "source_sha256": _sha256(pdf),
            "reference_kind": "LLAMA_GENERATED_CANDIDATE",
            "review_checklist": {
                "reading_order": "pending",
                "chapter_and_lesson_titles": "pending",
                "tables": "pending",
                "images_and_captions": "pending",
                "sampled_pages": "pending",
            },
            "human_review": {
                "approved_by": None,
                "approved_at": None,
                "reviewed_pages": [],
                "notes": "Correct the candidate against the source PDF before approval.",
            },
        }
    )

    destination = Path("benchmark/reviewed") / candidate_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare a human Ground Truth review packet")
    parser.add_argument("pdf_path")
    parser.add_argument("--reference-dir", default="benchmark/reference")
    args = parser.parse_args()
    print(prepare_review_packet(args.pdf_path, args.reference_dir))
