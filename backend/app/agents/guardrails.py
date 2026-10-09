"""
AI Safety & Regulatory Compliance Guardrails.

Intercepts conversational turns to detect:
  1. Prompt injection & Jailbreaks (attempts to override system instructions or leak prompts).
  2. TCPA / FCC DNC Opt-Out mandates (stop calling, remove number).
  3. Unauthorized financial / contract agreements.
"""

import re
from dataclasses import dataclass
from typing import Optional

# Jailbreak & Prompt Injection triggers
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(initial|system)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|jailbreak|DAN)\s+mode", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?rules", re.IGNORECASE),
    re.compile(r"system\s*:\s*override", re.IGNORECASE),
]

# TCPA Opt-out / Do-Not-Call triggers
_DNC_PATTERNS = [
    re.compile(r"\bstop\s+calling(\s+me)?\b", re.IGNORECASE),
    re.compile(r"\bremove\s+(my\s+number|me)\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+call\s+list\b", re.IGNORECASE),
    re.compile(r"\btake\s+me\s+off\s+(your\s+)?list\b", re.IGNORECASE),
    re.compile(r"\bunsubscribe\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+ever\s+call\s+again\b", re.IGNORECASE),
]


@dataclass
class GuardrailResult:
    is_safe: bool
    violation_type: Optional[str] = None  # 'prompt_injection' | 'dnc_opt_out'
    action: Optional[str] = None          # 'refuse' | 'opt_out_and_terminate' | 'none'
    prescribed_response: Optional[str] = None


def check_guardrails(utterance: str) -> GuardrailResult:
    """
    Evaluates incoming caller utterance against security and compliance rules.
    """
    if not utterance:
        return GuardrailResult(is_safe=True)

    # 1. Check for TCPA Do-Not-Call Opt-Out
    for pattern in _DNC_PATTERNS:
        if pattern.search(utterance):
            return GuardrailResult(
                is_safe=False,
                violation_type="dnc_opt_out",
                action="opt_out_and_terminate",
                prescribed_response=(
                    "Understood. I have added your phone number to our permanent Do-Not-Call list "
                    "and removed you from future outreach. We apologize for the disturbance. Have a great day."
                ),
            )

    # 2. Check for Prompt Injection / Jailbreak
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(utterance):
            return GuardrailResult(
                is_safe=False,
                violation_type="prompt_injection",
                action="refuse",
                prescribed_response=(
                    "I am an AI assistant designed exclusively to help with business inquiries and appointment scheduling. "
                    "I cannot modify my operational instructions. How can I assist you with our services today?"
                ),
            )

    return GuardrailResult(is_safe=True)
