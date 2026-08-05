"""
Educational Parser — Version 1 (rule-based, language-agnostic with OCR heuristics).

Input : clean Markdown from Docling / LlamaParse / OCR (# ## ### + paragraphs + tables).
Output: EducationalDocument (Pydantic) — Chapter -> Lesson -> Element.

Mapping:
    # Title      →  new Chapter
    ## Title     →  new Lesson inside current Chapter
    | … |        →  TABLE element
    Heuristic    →  HEADING element (for un-marked OCR text)
    other text   →  PARAGRAPH element

Built on heading-level layout and heuristic pattern matching.
The same code path handles Arabic, English, and any other language.
"""
from __future__ import annotations

import re

from schema.models import (
    Chapter,
    EducationalDocument,
    Element,
    ElementMetadata,
    ElementType,
    Lesson,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(?P<alt>.*?)\]\((?P<path>[^)]+)\)\s*$")
IMAGE_PLACEHOLDER_RE = re.compile(r"^<!--\s*image\s*-->$", re.IGNORECASE)
PAGE_MARKER_RE = re.compile(r"^<!--\s*page\s*:\s*(?P<page>\d+)\s*-->$", re.IGNORECASE)
OCR_CONFIDENCE_RE = re.compile(
    r"^<!--\s*ocr_confidence\s*:\s*(?P<confidence>\d+(?:\.\d+)?)\s*-->$",
    re.IGNORECASE,
)
ARABIC_CHAPTER_RE = re.compile(r"^(?:الفصل|الوحدة)\s+[\d\u0660-\u0669\u0600-\u06FF]+")
ARABIC_LESSON_RE = re.compile(r"^(?:الدرس|درس)\s+[\d\u0660-\u0669\u0600-\u06FF]+")

HEADING_PATTERNS = [
    re.compile(r"^(?:الفصل|درس|الدرس|الوحدة|Chapter|Lesson|Unit)\s+[\d\u0600-\u06FF]+", re.IGNORECASE),
    re.compile(r"^(\d+\.\d+)\s+"),  # 1.1, 2.3
    re.compile(r"^(\d+)\s+"),       # 1, 2
    re.compile(r"^[أ-ي]\."),        # أ. ب.
]


def detect_heading(text: str) -> tuple[bool, int]:
    """Detect heading status and level from un-marked text lines.

    Args:
        text: Input line string.

    Returns:
        Tuple of (is_heading, level).
    """
    clean_text = text.strip()
    if not clean_text:
        return False, 0

    if len(clean_text) < 80 and not clean_text.endswith("."):
        if ARABIC_CHAPTER_RE.match(clean_text):
            return True, 1
        if ARABIC_LESSON_RE.match(clean_text):
            return True, 2
        for pattern in HEADING_PATTERNS:
            if pattern.match(clean_text):
                if re.search(r"(فصل|الوحدة|Chapter|Unit)", clean_text, re.IGNORECASE):
                    return True, 1
                return True, 2

    return False, 0


def _parse_markdown_table_rows(lines: list[str]) -> list[list[str]] | None:
    """Parse clean pipe-table rows while preserving raw Markdown as fallback."""
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            return None
        # Markdown's separator row (| --- | :---: |) is not data.
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if len(rows) < 2 or len({len(row) for row in rows}) != 1:
        return None
    return rows


def parse_markdown_to_education(
    markdown_text: str,
    source_file: str,
    parser: str,
    language: str | None = None,
) -> EducationalDocument:
    """Convert a Markdown string into a structured EducationalDocument.

    Args:
        markdown_text: Markdown output from any BaseParser implementation.
        source_file:   Original file path (stored as provenance).
        parser:        Name of the parser that produced the Markdown.
        language:      ISO 639-1 language code when known (e.g. 'en', 'ar').
                       Pass None to remain language-agnostic.

    Returns:
        EducationalDocument ready for chunking or direct RAG ingestion.
    """
    doc = EducationalDocument(source_file=source_file, language=language, parser=parser)

    current_chapter: Chapter | None = None
    current_lesson: Lesson | None = None
    page = 1
    current_confidence: float | None = None

    def ensure_default_chapter() -> None:
        nonlocal current_chapter
        if current_chapter is None:
            current_chapter = Chapter(title="Untitled")
            doc.chapters.append(current_chapter)

    def ensure_default_lesson() -> None:
        nonlocal current_lesson
        ensure_default_chapter()
        if current_lesson is None:
            current_lesson = Lesson(title=current_chapter.title)
            current_chapter.lessons.append(current_lesson)

    def make_meta(chapter_title: str, lesson_title: str) -> ElementMetadata:
        extra = {}
        if current_confidence is not None:
            extra["needs_review"] = current_confidence < 0.60
        return ElementMetadata(
            page=page,
            chapter=chapter_title,
            lesson=lesson_title,
            parser=parser,
            confidence=current_confidence,
            extra=extra,
        )

    lines = markdown_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        page_match = PAGE_MARKER_RE.match(line)
        if page_match:
            page = int(page_match.group("page"))
            current_confidence = None
            i += 1
            continue

        confidence_match = OCR_CONFIDENCE_RE.match(line)
        if confidence_match:
            raw = float(confidence_match.group("confidence"))
            current_confidence = max(0.0, min(raw / 100.0, 1.0))
            i += 1
            continue

        image_match = IMAGE_RE.match(line)
        if image_match:
            ensure_default_lesson()
            alt_text = image_match.group("alt").strip() or "Image"
            current_lesson.elements.append(
                Element(
                    type=ElementType.IMAGE,
                    text=f"[Image: {alt_text}]",
                    metadata=make_meta(current_chapter.title, current_lesson.title).model_copy(
                        update={
                            "extra": {
                                **make_meta(current_chapter.title, current_lesson.title).extra,
                                "image_path": image_match.group("path"),
                                "alt_text": alt_text,
                            }
                        }
                    ),
                )
            )
            i += 1
            continue

        if IMAGE_PLACEHOLDER_RE.match(line):
            ensure_default_lesson()
            current_lesson.elements.append(
                Element(
                    type=ElementType.IMAGE,
                    text="[Image: Docling placeholder]",
                    metadata=make_meta(current_chapter.title, current_lesson.title).model_copy(
                        update={"extra": {"association": "docling_placeholder"}}
                    ),
                )
            )
            i += 1
            continue

        # --- Markdown Heading (# ## ###) ---
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if level == 1:
                current_chapter = Chapter(title=title)
                doc.chapters.append(current_chapter)
                current_lesson = None
            else:
                ensure_default_chapter()
                current_lesson = Lesson(title=title)
                current_chapter.lessons.append(current_lesson)

            ensure_default_lesson()
            current_lesson.elements.append(
                Element(
                    type=ElementType.HEADING,
                    text=title,
                    level=level,
                    metadata=make_meta(current_chapter.title, current_lesson.title),
                )
            )
            i += 1
            continue

        # --- Heuristic Heading (for un-marked OCR / plain text) ---
        is_heuristic_heading, level = detect_heading(line)
        if is_heuristic_heading:
            if level == 1:
                current_chapter = Chapter(title=line)
                doc.chapters.append(current_chapter)
                current_lesson = None
            else:
                ensure_default_chapter()
                current_lesson = Lesson(title=line)
                current_chapter.lessons.append(current_lesson)

            ensure_default_lesson()
            current_lesson.elements.append(
                Element(
                    type=ElementType.HEADING,
                    text=line,
                    level=level,
                    metadata=make_meta(current_chapter.title, current_lesson.title),
                )
            )
            i += 1
            continue

        # --- Markdown table (lines starting with |) ---
        if line.startswith("|"):
            table_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                table_lines.append(lines[j].strip())
                j += 1
            ensure_default_lesson()
            current_lesson.elements.append(
                Element(
                    type=ElementType.TABLE,
                    text="\n".join(table_lines),
                    format="rows" if _parse_markdown_table_rows(table_lines) else "markdown",
                    rows=_parse_markdown_table_rows(table_lines),
                    metadata=make_meta(current_chapter.title, current_lesson.title),
                )
            )
            i = j
            continue

        # --- Plain paragraph ---
        ensure_default_lesson()
        current_lesson.elements.append(
            Element(
                type=ElementType.PARAGRAPH,
                text=line,
                metadata=make_meta(current_chapter.title, current_lesson.title),
            )
        )
        i += 1

    return doc
