"""Zero-token pre-LLM input guardrails enforcing safety, injection, and INV-09 PII bounds."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ARABIC_ORTHOGRAPHY_TRANS = str.maketrans(
    {
        "\u0622": "\u0627",  # آ -> ا
        "\u0623": "\u0627",  # أ -> ا
        "\u0625": "\u0627",  # إ -> ا
        "\u0671": "\u0627",  # ٱ -> ا
        "\u0629": "\u0647",  # ة -> ه
        "\u0649": "\u064a",  # ى -> ي
    }
)
_DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_DISALLOWED_BIDI_CODEPOINTS = frozenset(
    {
        0x202A,  # LRE
        0x202B,  # RLE
        0x202C,  # PDF
        0x202D,  # LRO
        0x202E,  # RLO
        0x2066,  # LRI
        0x2067,  # RLI
        0x2068,  # FSI
        0x2069,  # PDI
    }
)

_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[\s-]?){11,18}\d(?!\d)")
_CARD_KEYWORD_RE = re.compile(
    r"\b(?:credit\s*card|debit\s*card|card\s*number|visa|mastercard|amex)\b"
    r"|(?:بطاقه\s*ائتمان|رقم\s*(?:البطاقه|الكارت)|فيزا|ماستركارد)",
    re.IGNORECASE,
)

_PII_PAYMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # CVV / CVC / security code
    re.compile(
        r"\b(?:cvv|cvc|cvv2|cid)\b\s*(?:is|:|=|#|-)?\s*\d{3,4}\b"
        r"|\bcard\s+security\s+code\b\s*(?:is|:|=)?\s*\d{3,4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:رمز\s+التحقق|رمز\s+الامان|كود\s+(?:الامان|البطاقه|الكارت)"
        r"|الرقم\s+السري\s+(?:للبطاقه|للكارت|للفيزا))\s*(?:هو|:|=)?\s*\d{3,4}\b"
    ),
    # Passwords / PINs
    re.compile(
        r"\b(?:password|passwd|pwd|passcode|pin\s+code|atm\s+pin)\b\s*(?:is|:|=)?\s*\S+"
        r"|\bpin\s*(?:is|:|=)\s*\d{4,8}\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:كلمه\s+(?:السر|المرور)|الباسورد|الرقم\s+السري)\s*(?:هو|هي|:|=)?\s*\S+"),
    # National IDs / SSN / Passport / Emirates ID
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b784-\d{4}-\d{7}-\d\b"),
    re.compile(r"\b[23]\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{7}\b"),
    re.compile(
        r"\b(?:national\s*id|ssn|social\s+security(?:\s+number)?|passport\s*(?:no|number)"
        r"|emirates\s*id|iqama(?:\s+number)?)\b\s*(?:is|number|no|:|=|#)?\s*[a-z0-9-]{6,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:الرقم\s+القومي|رقم\s+الهويه(?:\s+الوطنيه)?|رقم\s+الاقامه"
        r"|رقم\s+جواز\s+السفر|البطاقه\s+الشخصيه)\s*(?:هو|:|=)?\s*[a-z0-9-]{6,}",
        re.IGNORECASE,
    ),
)

_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # English injection & prompt extraction
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\s+"
        r"(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|system)?\s*"
        r"(?:instructions?|rules?|prompts?|directions?|guardrails?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|repeat|output|leak|dump|tell\s+me)\s+"
        r"(?:all\s+|me\s+)?(?:your\s+|the\s+)?"
        r"(?:system\s+prompt|hidden\s+instructions?|developer\s+prompt|initial\s+prompt"
        r"|internal\s+rules?|secret\s+instructions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:jailbreak|dan\s+mode|developer\s+mode\s+enabled"
        r"|act\s+as\s+(?:root|admin|system|an?\s+unrestricted))\b",
        re.IGNORECASE,
    ),
    re.compile(r"<\s*/?\s*(?:system|developer|prompt|instruction)\s*>", re.IGNORECASE),
    # Arabic injection & prompt extraction (after orthographic folding)
    re.compile(
        r"(?:تجاهل|انس|تخطي|تجاوز|الغي|الغاء)\s+"
        r"(?:كل\s+|جميع\s+)?(?:التعليمات|الاوامر|القواعد|القيود|الحمايه)\s*"
        r"(?:السابقه|اعلاه|الاساسيه|للنظام)?"
    ),
    re.compile(
        r"(?:اكشف|اعرض|اطبع|اخبرني|اظهر|وريني|قولي|هات)\s+"
        r"(?:لي\s+)?(?:تعليمات\s+النظام|البرومبت\s+(?:الاساسي|السري)"
        r"|رساله\s+النظام|التعليمات\s+المخفيه|اوامر\s+النظام|النص\s+الاساسي)"
    ),
    re.compile(r"تصرف\s+(?:وكانك|ك)\s*(?:مدير\s+النظام|بدون\s+قيود)"),
)


class GuardrailResult(BaseModel):
    """Result of zero-token pre-LLM safety, injection, and PII input checks."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    sanitized_message: str = ""
    reason_code: str | None = None
    language: Literal["ar", "en"] = "ar"


def detect_message_language(text: str) -> Literal["ar", "en"]:
    """Detect primary language ('ar' or 'en') from Unicode script characters."""
    if _ARABIC_CHAR_RE.search(text):
        return "ar"
    if _LATIN_CHAR_RE.search(text):
        return "en"
    return "ar"


def _has_disallowed_control_chars(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if code < 0x20 and ch not in ("\t", "\n", "\r"):
            return True
        if code == 0x7F or 0x80 <= code <= 0x9F:
            return True
        if code in _DISALLOWED_BIDI_CODEPOINTS:
            return True
    return False


def _passes_luhn(digits: str) -> bool:
    if not (13 <= len(digits) <= 19) or not digits.isdigit():
        return False
    if len(set(digits)) == 1 and digits[0] == "0":
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        val = ord(ch) - ord("0")
        if idx % 2 == 1:
            val *= 2
            if val > 9:
                val -= 9
        total += val
    return total % 10 == 0


def _normalize_for_inspection(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text).translate(_DIGIT_TRANS).lower()
    without_diacritics = _ARABIC_DIACRITICS_RE.sub("", nfkc)
    folded = without_diacritics.translate(_ARABIC_ORTHOGRAPHY_TRANS)
    return " ".join(folded.split())


def _contains_sensitive_pii_or_payment(normalized_text: str) -> bool:
    has_card_kw = _CARD_KEYWORD_RE.search(normalized_text) is not None
    for match in _CARD_CANDIDATE_RE.finditer(normalized_text):
        digits = re.sub(r"[\s-]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _passes_luhn(digits):
            return True
        if has_card_kw and 12 <= len(digits) <= 19:
            return True

    return any(pattern.search(normalized_text) is not None for pattern in _PII_PAYMENT_PATTERNS)


def _contains_prompt_injection(normalized_text: str) -> bool:
    return any(
        pattern.search(normalized_text) is not None for pattern in _PROMPT_INJECTION_PATTERNS
    )


def check_input_guardrails(message: str, *, max_chars: int = 1000) -> GuardrailResult:
    """Validate raw shopper text at 0 LLM tokens before DB access or workflow calls."""
    language = detect_message_language(message)

    if not message or not message.strip():
        return GuardrailResult(
            allowed=False,
            sanitized_message="",
            reason_code="empty_message",
            language=language,
        )

    if len(message) > max_chars:
        return GuardrailResult(
            allowed=False,
            sanitized_message="",
            reason_code="max_length_exceeded",
            language=language,
        )

    if _has_disallowed_control_chars(message):
        return GuardrailResult(
            allowed=False,
            sanitized_message="",
            reason_code="control_characters",
            language=language,
        )

    normalized = _normalize_for_inspection(message)
    if _contains_sensitive_pii_or_payment(normalized):
        return GuardrailResult(
            allowed=False,
            sanitized_message="",
            reason_code="sensitive_pii_payment",
            language=language,
        )

    if _contains_prompt_injection(normalized):
        return GuardrailResult(
            allowed=False,
            sanitized_message="",
            reason_code="prompt_injection",
            language=language,
        )

    sanitized = " ".join(message.split())
    return GuardrailResult(
        allowed=True,
        sanitized_message=sanitized,
        reason_code=None,
        language=language,
    )
