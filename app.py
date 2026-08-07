"""Local Streamlit viewer for the Educational RAG parsing pipeline.

Run with: ``streamlit run app.py``
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import fitz
import streamlit as st

from pipeline import run_pipeline

PAGE_MARKER_RE = re.compile(r"<!--\s*page\s*:\s*(\d+)\s*-->", re.IGNORECASE)


def _save_upload(uploaded_file) -> Path:
    destination = Path(tempfile.gettempdir()) / "ai_tutor_uploads"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / uploaded_file.name
    path.write_bytes(uploaded_file.getvalue())
    return path


def _markdown_for_page(markdown: str, page: int) -> str | None:
    markers = list(PAGE_MARKER_RE.finditer(markdown))
    if not markers:
        return None
    for index, match in enumerate(markers):
        if int(match.group(1)) == page:
            end = markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
            return markdown[match.end():end].strip()
    return "_No Markdown segment was emitted for this page._"


def _elements_as_markdown(document: dict, page: int) -> str:
    """Render only page-scoped structured elements when raw Markdown has no markers."""
    parts: list[str] = []
    for element in _elements_for_page(document, page):
        text = (element.get("text") or "").strip()
        if not text:
            continue
        if element.get("type") == "heading":
            parts.append(f"{'#' * min(element.get('level') or 2, 6)} {text}")
        elif element.get("type") == "image":
            parts.append(text)
        else:
            parts.append(text)
    return "\n\n".join(parts)


def _elements_for_page(document: dict, page: int) -> list[dict]:
    elements = []
    for chapter in document.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            for element in lesson.get("elements", []):
                if element.get("metadata", {}).get("page") == page:
                    elements.append(
                        {
                            "chapter": chapter.get("title"),
                            "lesson": lesson.get("title"),
                            **element,
                        }
                    )
    return elements


def _render_page(pdf_path: str, page_number: int) -> bytes:
    pdf = fitz.open(pdf_path)
    try:
        pixmap = pdf[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return pixmap.tobytes("png")
    finally:
        pdf.close()


st.set_page_config(page_title="AI Tutor Parse Studio", page_icon="📘", layout="wide")
st.title("📘 AI Tutor Parse Studio")
st.caption("Local Docling / Tesseract parser viewer — no cloud API required")

with st.sidebar:
    st.header("Document")
    uploaded = st.file_uploader("Upload a PDF textbook", type=["pdf"])
    st.caption("The pipeline automatically selects Docling, Tesseract, or local Qwen-VL from the PDF itself.")
    run = st.button("Parse document", type="primary", use_container_width=True, disabled=uploaded is None)
    st.divider()
    st.caption("JSON is the source of truth for Chunking. Markdown is a debug/review view.")

if run:
    if uploaded is None:
        st.sidebar.error("Upload a PDF first.")
    else:
        file_path = _save_upload(uploaded)
        with st.spinner("Parsing document. Large books can take several minutes..."):
            try:
                st.session_state["parse_result"] = run_pipeline(
                    str(file_path),
                    include_chunks=True,
                    include_markdown=True,
                    parsing_mode="auto",
                )
                st.session_state["pdf_path"] = str(file_path)
                st.session_state["pdf_name"] = uploaded.name
            except Exception as exc:
                st.exception(exc)

result = st.session_state.get("parse_result")
pdf_path = st.session_state.get("pdf_path")

if result and pdf_path:
    probe = result["probe"]
    document = result["educational_document"]
    markdown = result.get("raw_markdown", result.get("parser_markdown", ""))
    page_count = probe["num_pages"]

    with st.sidebar:
        st.success(f"Parser: {result['parser']}")
        st.write(f"Mode selected: `{result['parsing_mode']}`")
        st.write(f"Language: `{result['language']}`")
        page = st.number_input("Page", min_value=1, max_value=page_count, value=1, step=1)
        st.caption(f"{page_count} pages · {len(document.get('chapters', []))} chapters")

        st.download_button(
            "Download EducationalDocument JSON",
            data=json.dumps(document, ensure_ascii=False, indent=2),
            file_name=f"{Path(st.session_state['pdf_name']).stem}.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Download raw Markdown",
            data=markdown,
            file_name=f"{Path(st.session_state['pdf_name']).stem}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        if "chunks" in result:
            st.download_button(
                "Download chunks JSON",
                data=json.dumps(result["chunks"], ensure_ascii=False, indent=2),
                file_name=f"{Path(st.session_state['pdf_name']).stem}.chunks.json",
                mime="application/json",
                use_container_width=True,
            )

    left, right = st.columns([1.08, 1], gap="large")
    with left:
        st.subheader(f"PDF · page {page} of {page_count}")
        st.image(_render_page(pdf_path, int(page)), use_container_width=True)

    with right:
        st.subheader("Parsed result")
        markdown_tab, json_tab, quality_tab = st.tabs(["Markdown", "JSON", "Quality"])
        with markdown_tab:
            page_markdown = _markdown_for_page(markdown, int(page))
            if page_markdown is not None:
                st.markdown(page_markdown)
            else:
                fallback = _elements_as_markdown(document, int(page))
                st.caption("This parser did not emit raw page markers. Showing only structured elements associated with this page.")
                st.markdown(fallback or "_No page-scoped content is available for this page._")
        with json_tab:
            page_json = {"page": int(page), "elements": _elements_for_page(document, int(page))}
            st.json(page_json, expanded=False)
        with quality_tab:
            for metric, value in result["quality_report"].items():
                icon = "✅" if value["status"] == "PASS" else "⚠️"
                st.write(f"{icon} **{metric}** — {value['detail']}")

    with st.expander("Parser attempts and document metadata"):
        st.json(
            {
                "parser_attempts": result["parser_attempts"],
                "probe": probe,
                "chunk_count": result.get("chunk_count"),
                "refinement_report": result.get("refinement_report"),
            },
            expanded=False,
        )
else:
    st.info("Upload a PDF then choose **Parse document**. The page selector keeps the PDF, Markdown, and JSON view synchronized.")
