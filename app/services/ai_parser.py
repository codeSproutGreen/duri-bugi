import json
import logging
from datetime import datetime

import anthropic

from app.config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Korean financial message parser. Extract transaction details from Korean bank/card SMS and push notifications.

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:
{
  "transaction_type": "card_payment" | "bank_transfer" | "deposit" | "withdrawal" | "unknown",
  "amount": <integer, KRW, 0 if unknown>,
  "merchant": "<가맹점/상대방 name, empty string if unknown>",
  "card_or_account": "<카드/계좌 name extracted from message>",
  "date": "<YYYY-MM-DD or null if not determinable>",
  "memo": "<any extra info like 일시불, 할부, 잔액 etc.>",
  "suggested_debit_type": "asset" | "expense",
  "suggested_credit_type": "asset" | "liability" | "income",
  "confidence": <0.0 to 1.0>
}

Rules:
- card_payment: debit=expense(비용), credit=liability(카드미결제)
- deposit/income: debit=asset(은행계좌), credit=income(수입)
- withdrawal: debit=expense(비용), credit=asset(은행계좌)
- bank_transfer: debit=asset(받는계좌), credit=asset(보내는계좌)
- Amount must be integer (Korean Won has no decimals)
- For date, infer the year as current year if only MM/DD given
- If you cannot parse the message, set transaction_type to "unknown" and confidence to 0
"""


def _get_client():
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def parse_message(source_name: str, content: str) -> dict | None:
    """Parse a financial message using Claude API. Returns parsed dict or None."""
    if not settings.anthropic_api_key or settings.anthropic_api_key == "your-key-here":
        log.warning("Anthropic API key not configured")
        return None

    try:
        client = _get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        user_msg = f"today: {today}\nsource_name: {source_name}\nmessage: {content}"

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)
        log.info("AI parsed: type=%s amount=%s merchant=%s",
                 parsed.get("transaction_type"), parsed.get("amount"), parsed.get("merchant"))
        return parsed
    except json.JSONDecodeError as e:
        log.error("AI response not valid JSON: %s", e)
        return None
    except Exception as e:
        log.error("AI parse error: %s", e)
        return None


def parse_messages_batch(messages: list[tuple[str, str]]) -> list[dict | None]:
    """Parse multiple messages in a single API call for cost efficiency.
    Each tuple is (source_name, content). Returns list of parsed dicts."""
    if not messages:
        return []
    if len(messages) == 1:
        return [parse_message(messages[0][0], messages[0][1])]

    if not settings.anthropic_api_key or settings.anthropic_api_key == "your-key-here":
        return [None] * len(messages)

    try:
        client = _get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        numbered = "\n\n".join(
            f"[{i+1}]\nsource_name: {src}\nmessage: {content}"
            for i, (src, content) in enumerate(messages)
        )
        user_msg = f"today: {today}\nParse each message below and return a JSON array with one object per message in order:\n\n{numbered}"

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT + "\nWhen given multiple messages, return a JSON array of objects.",
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        results = json.loads(text)
        if isinstance(results, list):
            return results
        return [results]
    except Exception as e:
        log.error("Batch parse error: %s", e)
        return [None] * len(messages)
