from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core import guidance_service
from scripts import extract_guidance_claims


class _FakeBlock:
    def __init__(self, text: str, type: str = "text") -> None:
        self.text = text
        self.type = type


class _FakeThinkingBlock:
    """A non-text block with no ``.text`` attribute, as a thinking block has."""

    def __init__(self, thinking: str = "") -> None:
        self.thinking = thinking
        self.type = "thinking"


class FakeMessage:
    def __init__(self, content: list[object]) -> None:
        self.content = content


class FakeMessagesClient:
    def __init__(self, content: list[object]) -> None:
        self._content = content
        self.last_call_kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> FakeMessage:
        self.last_call_kwargs = kwargs
        return FakeMessage(self._content)


class FakeAnthropicClient:
    def __init__(self, response_text: str, *, leading_blocks: list[object] | None = None) -> None:
        content = list(leading_blocks or []) + [_FakeBlock(response_text)]
        self.messages = FakeMessagesClient(content)


class ExtractGuidanceClaimsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        shutil.copy(ROOT / "data" / "company_master.csv", self.data_dir / "company_master.csv")

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

        self.doc_id = guidance_service.register_source_document(
            ticker="2330.TW",
            file_path="data/raw_transcripts/2330.TW/114Q2.pdf",
            source_quarter="114Q2",
            call_date="2025-07-18",
        )["doc_id"]

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_parse_llm_response_handles_plain_json(self) -> None:
        raw_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "revenue up 10-15%%"}]'
        )
        parsed = extract_guidance_claims.parse_llm_response(raw_text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "revenue_growth")

    def test_parse_llm_response_strips_markdown_fences(self) -> None:
        raw_text = '```json\n[{"target_period": "114Q3", "category": "capex", ' \
            '"product_or_segment": null, "direction": "up", "quant_low": null, ' \
            '"quant_high": null, "raw_text": "capex increases"}]\n```'
        parsed = extract_guidance_claims.parse_llm_response(raw_text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "capex")

    def test_parse_llm_response_rejects_non_json(self) -> None:
        with self.assertRaises(ValueError):
            extract_guidance_claims.parse_llm_response("not json at all")

    def test_extract_claims_for_document_stores_pending_claims(self) -> None:
        response_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "We expect Q3 revenue to grow 10-15%% sequentially."},'
            '{"target_period": "114Q3", "category": "product_line", '
            '"product_or_segment": "Advanced Packaging", "direction": "up", '
            '"quant_low": null, "quant_high": null, "raw_text": "Advanced packaging demand is strong."}]'
        )
        fake_client = FakeAnthropicClient(response_text)

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            count = extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        self.assertEqual(count, 2)
        pending = guidance_service.load_guidance_claims(status="pending_review")
        self.assertEqual(len(pending), 2)
        self.assertIn("revenue_growth", pending["category"].tolist())
        self.assertIn("product_line", pending["category"].tolist())
        self.assertEqual(fake_client.messages.last_call_kwargs["model"], "claude-sonnet-5")

    def test_extract_claims_selects_text_block_after_a_thinking_block(self) -> None:
        response_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "We expect Q3 revenue to grow 10-15%% sequentially."}]'
        )
        # A thinking block precedes the text block: response.content[0].text
        # would raise AttributeError, type-based selection must still work.
        fake_client = FakeAnthropicClient(
            response_text,
            leading_blocks=[_FakeThinkingBlock("deliberating about the transcript")],
        )

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            count = extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        self.assertEqual(count, 1)
        self.assertEqual(len(guidance_service.load_guidance_claims(status="pending_review")), 1)

    def test_extract_claims_raises_when_no_text_block_present(self) -> None:
        fake_client = FakeAnthropicClient("unused")
        fake_client.messages = FakeMessagesClient([_FakeThinkingBlock("no text block at all")])

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            with self.assertRaises(ValueError):
                extract_guidance_claims.extract_claims_for_document(
                    fake_client,
                    doc_id=self.doc_id,
                    ticker="2330.TW",
                    source_quarter="114Q2",
                    pdf_path=Path("fake.pdf"),
                )

    def test_extract_claims_disables_thinking_and_uses_a_large_output_budget(self) -> None:
        fake_client = FakeAnthropicClient("[]")

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        kwargs = fake_client.messages.last_call_kwargs
        self.assertEqual(kwargs["thinking"], {"type": "disabled"})
        self.assertGreaterEqual(kwargs["max_tokens"], 16000)

    def test_extract_claims_skips_malformed_elements_without_crashing(self) -> None:
        response_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "We expect Q3 revenue to grow 10-15%% sequentially."},'
            '{"target_period": "114Q3", "category": "capex", '
            '"product_or_segment": null, "direction": "up", '
            '"quant_low": null, "quant_high": null}]'  # missing "raw_text"
        )
        fake_client = FakeAnthropicClient(response_text)

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            count = extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        self.assertEqual(count, 1)
        pending = guidance_service.load_guidance_claims(status="pending_review")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.iloc[0]["category"], "revenue_growth")

    def test_extract_claims_skips_non_dict_elements_without_crashing(self) -> None:
        response_text = (
            '["not a dict",'
            '{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "We expect Q3 revenue to grow 10-15%% sequentially."}]'
        )
        fake_client = FakeAnthropicClient(response_text)

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            count = extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        self.assertEqual(count, 1)
        self.assertEqual(len(guidance_service.load_guidance_claims(status="pending_review")), 1)


if __name__ == "__main__":
    unittest.main()
