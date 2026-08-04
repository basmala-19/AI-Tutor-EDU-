"""
Download the ParseBench dataset from HuggingFace.

Dataset: https://huggingface.co/datasets/llamaindex/ParseBench

Structure after download:
    <local_dir>/
    ├── chart.jsonl
    ├── layout.jsonl
    ├── table.jsonl
    ├── text_content.jsonl
    ├── text_formatting.jsonl
    └── docs/{chart,layout,table,text}/*.pdf
"""
from __future__ import annotations

from pathlib import Path

DATASET_REPO = "llamaindex/ParseBench"
DATASET_REPO_TYPE = "dataset"
TEST_DATA_REVISION = "test-data"

DEFAULT_DATA_DIR = Path("./data")
DEFAULT_TEST_DATA_DIR = Path("./data/test")

# Files that must exist for the dataset to be considered complete
_REQUIRED_FILES = [
    "chart.jsonl",
    "layout.jsonl",
    "table.jsonl",
    "text_content.jsonl",
    "text_formatting.jsonl",
]

# At least one document must exist per category
_REQUIRED_DOC_DIRS = ["docs/chart", "docs/layout", "docs/table", "docs/text"]


def default_data_dir(test: bool = False) -> Path:
    """Return the default on-disk path for the given download mode.

    Args:
        test: When True, returns the test-slice directory.

    Returns:
        Path to the appropriate data directory.
    """
    return DEFAULT_TEST_DATA_DIR if test else DEFAULT_DATA_DIR


def is_dataset_ready(data_dir: Path) -> bool:
    """Check whether the dataset is already downloaded and structurally complete.

    Args:
        data_dir: Path to the data directory.

    Returns:
        True when all required JSONL files exist and each category has at least one PDF.
    """
    if not data_dir.exists():
        return False

    for f in _REQUIRED_FILES:
        if not (data_dir / f).exists():
            return False

    for d in _REQUIRED_DOC_DIRS:
        doc_dir = data_dir / d
        if not doc_dir.exists():
            return False
        if not any(doc_dir.rglob("*.*")):
            return False

    return True


def download_dataset(
    data_dir: Path | None = None,
    force: bool = False,
    test: bool = False,
) -> Path:
    """Download the ParseBench dataset from HuggingFace.

    Uses huggingface_hub's snapshot_download to fetch all JSONL files and PDFs.

    Args:
        data_dir: Local directory for the dataset.
                  Defaults to ./data (or ./data/test when test=True).
        force:    Re-download even if the data already exists.
        test:     Download the small test slice (3 files per category).

    Returns:
        Path to the ready dataset directory.

    Raises:
        RuntimeError: When download completes but validation still fails.
    """
    from huggingface_hub import snapshot_download

    if data_dir is None:
        data_dir = default_data_dir(test=test)

    revision = TEST_DATA_REVISION if test else None

    if not force and is_dataset_ready(data_dir):
        print(f"Dataset already present at: {data_dir}")
        return data_dir

    label = "test slice" if test else "full dataset"
    print(f"Downloading {label} from HuggingFace: {DATASET_REPO}")
    if test:
        print(f"  Branch: {TEST_DATA_REVISION}")
    print(f"  Destination: {data_dir}")

    snapshot_download(
        repo_id=DATASET_REPO,
        repo_type=DATASET_REPO_TYPE,
        local_dir=str(data_dir),
        revision=revision,
    )

    if not is_dataset_ready(data_dir):
        raise RuntimeError(
            f"Download completed but validation failed. Check {data_dir} for missing files."
        )

    print(f"Dataset ready at: {data_dir}")
    return data_dir
