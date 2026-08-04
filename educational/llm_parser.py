"""
Educational Parser — Version 2 (LLM-based, language-agnostic).

Difference from rule_based_parser.py:
  V1 classifies elements purely from Markdown structure:  # → heading, | → table.
  V2 sends the Markdown to an LLM (e.g. Qwen2.5) to classify each segment into:
  example / exercise / definition / concept — not just heading / paragraph.

This is a typed placeholder. The Router and pipeline are already ready to accept
it without changes to any other module — just pass an instance to the pipeline
instead of using parse_markdown_to_education().
"""
from schema.models import EducationalDocument

EDUCATIONAL_EXTRACTION_PROMPT = """\
Convert this lesson text into a structured educational JSON.
Classify each text segment as one of: heading, paragraph, definition, example, exercise.
Preserve the original language — do not translate.

Text:
{markdown_chunk}

Return only valid JSON matching this schema:
{"type": "...", "text": "..."}
"""


class LLMEducationalParser:
    """LLM-based educational parser — requires a configured LLM client.

    Not yet implemented. This placeholder documents the planned V2 interface
    so the team knows what to build next and in which module.

    Suggested backend: Qwen2.5-7B via Ollama (local) or a cloud API.
    """

    def __init__(self, model_client=None) -> None:
        self.model_client = model_client

    def parse(
        self,
        markdown_text: str,
        source_file: str,
        language: str | None = None,
    ) -> EducationalDocument:
        raise NotImplementedError(
            "V2 LLM parser is not implemented yet. "
            "Wire up a model client (Qwen2.5 / Ollama / API) and implement "
            "this method. Return type must match rule_based_parser so the "
            "chunker and evaluation layer require no changes."
        )
