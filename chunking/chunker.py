"""
Chunking over structured EducationalDocument — not raw Markdown.

Each chunk carries chapter / lesson / page / parser as ready-made metadata,
so retrieval never needs to re-infer context from plain text.

Design decisions:
  - TABLE and HEADING always get their own chunk (never split mid-table).
  - PARAGRAPH elements are buffered up to max_chars then flushed.
  - Chunking is an *optional* step; the pipeline stops at EducationalDocument
    by default and only calls this module when include_chunks=True.
"""
from schema.models import EducationalDocument, ElementType


def chunk_educational_document(
    doc: EducationalDocument, max_chars: int = 500
) -> list[dict]:
    """Split an EducationalDocument into retrieval-ready chunks.

    Args:
        doc:       Structured document produced by any Educational Parser.
        max_chars: Soft character limit per paragraph chunk.

    Returns:
        List of dicts, each with keys: text, type, chapter, lesson, page, parser.
    """
    chunks: list[dict] = []

    for chapter_title, lesson_title, elements in _iter_lessons(doc):
        buffer: list[str] = []
        buffer_len = 0
        buffer_page: int | None = None

        def flush() -> None:
            if buffer:
                chunks.append(
                    {
                        "text": "\n".join(buffer),
                        "type": "paragraph",
                        "chapter": chapter_title,
                        "lesson": lesson_title,
                        "page": buffer_page,
                        "parser": elements[0].metadata.parser if elements else None,
                    }
                )

        for el in elements:
            piece = el.text or ""

            # Tables, headings, and figures are always standalone chunks.
            if el.type in (ElementType.TABLE, ElementType.HEADING, ElementType.IMAGE):
                flush()
                buffer, buffer_len, buffer_page = [], 0, None
                chunk = {
                        "text": piece,
                        "type": el.type.value,
                        "chapter": chapter_title,
                        "lesson": lesson_title,
                        "page": el.metadata.page,
                        "parser": el.metadata.parser,
                    }
                if el.type == ElementType.IMAGE:
                    chunk["image_path"] = el.metadata.extra.get("image_path")
                    chunk["alt_text"] = el.metadata.extra.get("alt_text")
                chunks.append(chunk)
                continue

            if buffer_len + len(piece) > max_chars:
                flush()
                buffer, buffer_len, buffer_page = [], 0, None

            if buffer_page is None:
                buffer_page = el.metadata.page
            buffer.append(piece)
            buffer_len += len(piece)

        flush()

    return chunks


def _iter_lessons(doc: EducationalDocument):
    """Yield (chapter_title, lesson_title, element_list) for every lesson."""
    for chapter in doc.chapters:
        for lesson in chapter.lessons:
            yield chapter.title, lesson.title, lesson.elements
