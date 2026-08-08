from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import guidance_service

EXTRACTION_PROMPT_TEMPLATE = """You are extracting forward-looking claims from a Taiwan-listed company's earnings call transcript.

Only extract statements that describe expectations for a FUTURE reporting period (guidance, product-line outlook). Do not extract statements that merely restate already-published historical results.

Return a JSON array. Each element must have exactly these fields:
- "target_period": the future quarter the claim is about, formatted like "114Q3" (ROC year + quarter). Infer this from context if not stated explicitly.
- "category": one of "revenue_growth", "gross_margin", "product_line", "capex", "other"
- "product_or_segment": the product line or segment name if the claim is about one, otherwise null
- "direction": one of "up", "down", "flat"
- "quant_low": the low end of any quantitative range management gave, as a number, otherwise null
- "quant_high": the high end of any quantitative range management gave, as a number, otherwise null
- "raw_text": the verbatim excerpt this claim was extracted from

Return ONLY the JSON array, no other text.

Transcript:
{transcript_text}
"""


def extract_text_from_pdf(path: Path) -> str:
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return "\n".join(pages_text)


def build_extraction_prompt(transcript_text: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(transcript_text=transcript_text)


def parse_llm_response(raw_text: str) -> list[dict]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json"):]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("LLM response must be a JSON array of claims")
    return parsed


def extract_claims_for_document(
    client,
    *,
    doc_id: str,
    ticker: str,
    source_quarter: str,
    pdf_path: Path,
    model: str = "claude-sonnet-5",
) -> int:
    transcript_text = extract_text_from_pdf(pdf_path)
    prompt = build_extraction_prompt(transcript_text)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = response.content[0].text
    parsed_claims = parse_llm_response(raw_text)

    count = 0
    for parsed in parsed_claims:
        guidance_service.add_claim(
            doc_id=doc_id,
            ticker=ticker,
            source_quarter=source_quarter,
            target_period=parsed["target_period"],
            category=parsed["category"],
            product_or_segment=parsed.get("product_or_segment"),
            direction=parsed["direction"],
            quant_low=parsed.get("quant_low"),
            quant_high=parsed.get("quant_high"),
            raw_text=parsed["raw_text"],
        )
        count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract guidance claims from an earnings call PDF via the Claude API.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--source-quarter", required=True, help="Quarter the call was held for, e.g. 114Q2")
    parser.add_argument("--pdf-path", required=True, type=Path)
    parser.add_argument("--call-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args(argv)

    import anthropic

    client = anthropic.Anthropic()

    doc = guidance_service.register_source_document(
        ticker=args.ticker,
        file_path=str(args.pdf_path),
        source_quarter=args.source_quarter,
        call_date=args.call_date,
    )
    count = extract_claims_for_document(
        client,
        doc_id=doc["doc_id"],
        ticker=args.ticker,
        source_quarter=args.source_quarter,
        pdf_path=args.pdf_path,
        model=args.model,
    )
    print(f"Extracted {count} pending claim(s) from {args.pdf_path}")


if __name__ == "__main__":
    main()
