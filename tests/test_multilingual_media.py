"""Regression coverage for Arabic, page markers, and RAG image chunks."""
from educational.rule_based_parser import parse_markdown_to_education
from chunking.chunker import chunk_educational_document
from schema.models import ElementType


ARABIC_CHAPTER = "\u0627\u0644\u0641\u0635\u0644 \u0627\u0644\u0623\u0648\u0644: \u0627\u0644\u0643\u0633\u0648\u0631"
ARABIC_LESSON = "\u0627\u0644\u062f\u0631\u0633 \u0627\u0644\u0623\u0648\u0644: \u0645\u0642\u0627\u0631\u0646\u0629 \u0627\u0644\u0643\u0633\u0648\u0631"


def test_real_arabic_unmarked_headings_are_structured():
    markdown = f"{ARABIC_CHAPTER}\n\n{ARABIC_LESSON}\n\n\u0646\u0635 \u062a\u0639\u0644\u064a\u0645\u064a.\n"
    document = parse_markdown_to_education(markdown, "math-ar.pdf", "docling", "ar")

    assert document.language == "ar"
    assert document.chapters[0].title == ARABIC_CHAPTER
    assert ARABIC_LESSON in [lesson.title for lesson in document.chapters[0].lessons]


def test_markdown_image_keeps_page_and_retrieval_context():
    markdown = """# Biology

## Cell

<!-- page: 16 -->
![Cell diagram](assets/cell.png)
"""
    document = parse_markdown_to_education(markdown, "biology.pdf", "docling", "en")
    image = next(element for element, _, _ in document.all_elements() if element.type == ElementType.IMAGE)
    chunks = chunk_educational_document(document)
    image_chunk = next(chunk for chunk in chunks if chunk["type"] == "image")

    assert image.metadata.page == 16
    assert image.metadata.extra["image_path"] == "assets/cell.png"
    assert image_chunk["chapter"] == "Biology"
    assert image_chunk["lesson"] == "Cell"
    assert image_chunk["image_path"] == "assets/cell.png"


def test_docling_image_placeholder_is_an_image_not_a_paragraph():
    document = parse_markdown_to_education(
        "# Biology\n\n## Cell\n\n<!-- image -->", "biology.pdf", "docling", "en"
    )
    element = document.all_elements()[-1][0]
    assert element.type == ElementType.IMAGE
    assert element.metadata.extra["association"] == "docling_placeholder"


def test_clean_pipe_table_has_structured_rows():
    document = parse_markdown_to_education(
        "# Math\n\n## Data\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
        "math.pdf",
        "docling",
        "en",
    )
    table = next(el for el, _, _ in document.all_elements() if el.type == ElementType.TABLE)
    assert table.format == "rows"
    assert table.rows == [["A", "B"], ["1", "2"]]


def test_noisy_tesseract_pipe_text_is_not_promoted_to_a_table():
    document = parse_markdown_to_education(
        "| OCR noise |\n| broken", "scan.pdf", "tesseract", "en"
    )
    assert all(element.type != ElementType.TABLE for element, _, _ in document.all_elements())
