"""LiteParse adapter tests without downloading the external package."""

import sys
import types

from parsers.liteparse_parser import LiteParseParser


def test_liteparse_adapter_returns_markdown(monkeypatch, tmp_path):
    class FakeLiteParse:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def parse(self, _):
            return types.SimpleNamespace(
                text="# Chapter\n\nText",
                pages=[types.SimpleNamespace(page_num=1, text_items=[types.SimpleNamespace(text="Page one")])],
            )

    monkeypatch.setitem(sys.modules, "liteparse", types.SimpleNamespace(LiteParse=FakeLiteParse))
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"fake")
    parser = LiteParseParser()
    assert parser.parse(str(pdf)) == "# Chapter\n\nText"
    assert parser.last_page_text == {1: "Page one"}
