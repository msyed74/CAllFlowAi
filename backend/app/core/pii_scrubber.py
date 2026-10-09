"""
PII Scrubbing & Data Masking Engine.

Redacts sensitive Personally Identifiable Information (PII) and Payment Card Industry (PCI)
data from logs and call transcripts prior to persistent storage:
  - Credit Card Numbers (Visa, Mastercard, Amex, Discover)
  - US Social Security Numbers (SSN)
  - API Keys and Secrets (OpenAI, Twilio, JWT tokens)
  - Email addresses (optional masking)
"""

import re
from typing import Optional

# Regular expressions for sensitive patterns
_CREDIT_CARD_REGEX = re.compile(
    r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"
)
_SSN_REGEX = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_JWT_TOKEN_REGEX = re.compile(r"\beyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\b")
_API_KEY_REGEX = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|AC[a-f0-9]{32}|SK[a-f0-9]{32})\b")


def scrub_pii(text: Optional[str], mask_emails: bool = False) -> str:
    """
    Sanitizes string by replacing sensitive entities with redaction placeholders.
    """
    if not text:
        return ""

    sanitized = text

    # Redact API Keys & Secrets
    sanitized = _API_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)

    # Redact JWT Tokens
    sanitized = _JWT_TOKEN_REGEX.sub("[REDACTED_JWT]", sanitized)

    # Redact Credit Cards
    sanitized = _CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", sanitized)

    # Redact SSNs
    sanitized = _SSN_REGEX.sub("[REDACTED_SSN]", sanitized)

    # Optional email masking
    if mask_emails:
        sanitized = _EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)

    return sanitized
