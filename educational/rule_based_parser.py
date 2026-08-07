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
from html.parser import HTMLParser

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
HTML_TABLE_START_RE = re.compile(r"^<table(?:\s|>)", re.IGNORECASE)
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

# Tesseract often merges a coloured textbook banner with nearby body text into
# one long line. Recover the banner as structure, but retain the full OCR line
# as a paragraph so this heuristic can never discard educational content.
_ARABIC_ORDINAL = r"(?:\u0627\u0644\u0623\u0648\u0644|\u0627\u0644\u0627\u0648\u0644|\u0627\u0644\u062b\u0627\u0646\u064a|\u0627\u0644\u062b\u0627\u0646\u0649|\u0627\u0644\u062b\u0627\u0644\u062b|\u0627\u0644\u0631\u0627\u0628\u0639|\u0627\u0644\u062e\u0627\u0645\u0633|\u0627\u0644\u0633\u0627\u062f\u0633|\u0627\u0644\u0633\u0627\u0628\u0639|\u0627\u0644\u062b\u0627\u0645\u0646|\u0627\u0644\u062a\u0627\u0633\u0639|\u0627\u0644\u0639\u0627\u0634\u0631|[0-9\u0660-\u0669]+)"
_OCR_ARABIC_CHAPTER_EMBEDDED_RE = re.compile(
    rf"(?P<title>(?:\u0627\u0644\u0628\u0627\u0628|\u0627\u0644\u0641\u0635\u0644|\u0627\u0644\u0648\u062d\u062f\u0629)\s*{_ARABIC_ORDINAL}(?:\s*[0-9\u0660-\u0669]+)?(?:\s*[-:\u2013\u2014]?\s*[\u0621-\u064A]{2,}){{0,8}})"
)
_OCR_ARABIC_SECTION_EMBEDDED_RE = re.compile(
    rf"(?P<title>(?:\u0627\u0644\u0641\u0635\u0644|\u0627\u0644\u0648\u062d\u062f\u0629)\s*{_ARABIC_ORDINAL}(?:\s*[0-9\u0660-\u0669]+)?(?:\s*[-:\u2013\u2014]?\s*[\u0621-\u064A]{2,}){{0,8}})"
)
_OCR_ARABIC_LESSON_EMBEDDED_RE = re.compile(
    rf"(?P<title>(?:\u0627\u0644\u062f\u0631\u0633|\u062f\u0631\u0633)\s*{_ARABIC_ORDINAL}(?:\s*[0-9\u0660-\u0669]+)?(?:\s*[-:\u2013\u2014]?\s*[\u0621-\u064A]{2,}){{0,8}})"
)
_OCR_TITLE_STOP_RE = re.compile(
    r"\s+(?:\u0641\u064a\s+\u0646\u0647\u0627\u064a\u0629|\u0623\u0647\u062f\u0627\u0641|\u064a\u062a\u0639\u0631\u0641|\u064a\u062a\u0639\u0644\u0645|\u0646\u0634\u0627\u0637|\u062a\u062f\u0631\u064a\u0628|\u0627\u062e\u062a\u0631|\u0639\u0644\u0644|\u0645\u0627\u0630\u0627|\u0623\u0633\u0626\u0644\u0629)\b"
)


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


def recover_ocr_arabic_heading(text: str, parser: str, language: str | None) -> tuple[str, int] | None:
    """Recover a chapter or lesson banner embedded in Arabic OCR text."""
    if parser != "tesseract" or language != "ar" or len(text) < 8:
        return None

    # Prefer "chapter"/"unit" over an earlier "part" (باب), because a
    # banner commonly contains both and the chapter is the RAG hierarchy key.
    preferred = _OCR_ARABIC_SECTION_EMBEDDED_RE.search(text)
    if preferred and preferred.start() <= 160:
        candidates: list[tuple[int, re.Match[str]]] = [(1, preferred)]
    else:
        candidates = []
    if not candidates:
        for level, pattern in ((1, _OCR_ARABIC_CHAPTER_EMBEDDED_RE), (2, _OCR_ARABIC_LESSON_EMBEDDED_RE)):
            match = pattern.search(text)
            if match and match.start() <= 160:
                candidates.append((level, match))
    if not candidates:
        return None

    level, match = min(candidates, key=lambda item: item[1].start())
    title = _OCR_TITLE_STOP_RE.split(match.group("title"), maxsplit=1)[0]
    title = re.sub(r"\s+", " ", title).strip(" -:\u2013\u2014")
    return (title, level) if len(title) >= 7 else None


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


def _has_markdown_table_separator(lines: list[str]) -> bool:
    """A separator row distinguishes real Markdown from OCR pipe noise."""
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            return True
    return False


class _HTMLTableReader(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.headers: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._header_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._header_cell = tag == "th"

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            if self._header_cell:
                self.headers.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _parse_html_table(html: str) -> tuple[list[list[str]] | None, list[str]]:
    reader = _HTMLTableReader()
    reader.feed(html)
    rows = reader.rows or None
    return rows, reader.headers


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

        if HTML_TABLE_START_RE.match(line):
            table_lines = [line]
            j = i + 1
            while j < len(lines):
                table_lines.append(lines[j])
                if "</table>" in lines[j].lower():
                    j += 1
                    break
                j += 1
            raw_html = "\n".join(table_lines)
            rows, headers = _parse_html_table(raw_html)
            ensure_default_lesson()
            current_lesson.elements.append(
                Element(
                    type=ElementType.TABLE,
                    text=raw_html,
                    format="html",
                    rows=rows,
                    metadata=make_meta(current_chapter.title, current_lesson.title).model_copy(
                        update={"extra": {"headers": headers, "rows": rows or []}}
                    ),
                )
            )
            i = j
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

        # --- Arabic heading embedded in a long OCR line ---
        recovered_heading = recover_ocr_arabic_heading(line, parser, language)
        if recovered_heading:
            title, level = recovered_heading
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
            # Continue into paragraph handling below: objective/body text that
            # shares the OCR line must remain retrievable.

        # --- Heuristic Heading (for un-marked OCR / plain text) ---
        is_heuristic_heading, level = (False, 0) if recovered_heading else detect_heading(line)
        # OCR body text often begins with a stray page/question number.  Bare
        # numeric-prefix headings are useful for clean digital Markdown, but
        # create false lessons such as "2 9 ..." in scanned Arabic books.
        if parser == "tesseract" and re.match(r"^[0-9\u0660-\u0669]", line):
            is_heuristic_heading, level = False, 0
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
            parsed_rows = _parse_markdown_table_rows(table_lines)
            # OCR noise can contain stray pipe characters.  Unlike Docling
            # Markdown, it is not evidence of a table unless rows are valid.
            if parser == "tesseract" and (parsed_rows is None or not _has_markdown_table_separator(table_lines)):
                current_lesson.elements.append(
                    Element(
                        type=ElementType.PARAGRAPH,
                        text="\n".join(table_lines),
                        metadata=make_meta(current_chapter.title, current_lesson.title),
                    )
                )
                i = j
                continue
            current_lesson.elements.append(
                Element(
                    type=ElementType.TABLE,
                    text="\n".join(table_lines),
                    format="rows" if parsed_rows else "markdown",
                    rows=parsed_rows,
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
