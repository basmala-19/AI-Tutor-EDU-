"""
Reference Reviewer — validates reference structures and promotes them to official Ground Truth.

Pipeline Workflow:
    PDF Document
        ↓
    generate_reference.py  (candidate structure -> benchmark/reference/)
        ↓
    review_reference.py    (validation & promotion -> benchmark/ground_truth/)
        ↓
    evaluator.py           (evaluates pipeline against official Ground Truth)
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def review_and_promote(
    reference_dir: str = "benchmark/reviewed",
    ground_truth_dir: str = "benchmark/ground_truth",
) -> list[dict]:
    """Validate reference documents and promote approved references to Ground Truth JSONs.

    Args:
        reference_dir: Path to raw reference JSON files.
        ground_truth_dir: Path to output official Ground Truth JSON files.

    Returns:
        List of validated Ground Truth document dictionaries.
    """
    os.makedirs(ground_truth_dir, exist_ok=True)
    if not os.path.exists(reference_dir):
        print(f"Reference directory not found: {reference_dir}")
        return []

    promoted = []
    files = sorted(Path(reference_dir).glob("*.json"))

    print(f"Reviewing {len(files)} reference documents for Ground Truth promotion...")

    for ref_file in files:
        with open(ref_file, "r", encoding="utf-8") as f:
            ref = json.load(f)

        # Parser output is an annotation candidate, not ground truth.  Require
        # an explicit human review record before it can affect evaluation.
        review = ref.get("human_review", {})
        valid = True
        if not ref.get("source_file") or not ref.get("chapters"):
            valid = False
        if not review.get("approved_by") or not review.get("approved_at"):
            valid = False
        if not ref.get("source_sha256"):
            valid = False
        if any(status != "passed" for status in ref.get("review_checklist", {}).values()):
            valid = False

        for ch in ref.get("chapters", []):
            if not ch.get("title") or "lessons" not in ch:
                valid = False
                break

        if valid:
            gt_doc = {
                "source_file": ref["source_file"],
                "language": ref.get("language", "auto"),
                "num_pages": ref.get("num_pages", 0),
                "status": "HUMAN_VERIFIED_GROUND_TRUTH",
                "human_review": review,
                "source_sha256": ref["source_sha256"],
                "review_checklist": ref["review_checklist"],
                "chapters": ref["chapters"],
            }
            out_file = os.path.join(ground_truth_dir, ref_file.name)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(gt_doc, f, indent=2, ensure_ascii=False)

            promoted.append(gt_doc)
            print(f"[PROMOTED] {ref['source_file']} -> {ref_file.name}")
        else:
            print(f"[REJECTED] {ref_file.name}: failed validation rules")

    print(f"Promotion Complete: {len(promoted)}/{len(files)} reference documents verified as Official Ground Truth.")
    return promoted


if __name__ == "__main__":
    review_and_promote()
