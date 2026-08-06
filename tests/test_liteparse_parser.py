"""LiteParse adapter tests without downloading the external package."""

import sys
import types

from parsers.liteparse_parser import LiteParseParser


def test_liteparse_adapter_returns_markdown(monkeypatch, tmp_path):
    class FakeLiteParse:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def parse(self, _):
            return types.SimpleNamespace(text="# Chapter\n\nText")

    monkeypatch.setitem(sys.modules, "liteparse", types.SimpleNamespace(LiteParse=FakeLiteParse))
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"fake")
    assert LiteParseParser().parse(str(pdf)) == "# Chapter\n\nText"
