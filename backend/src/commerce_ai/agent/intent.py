"""Bounded Call #1 bilingual intent extraction with deterministic rule-based fallback."""

import json
import math
import re
import unicodedata
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce_ai.agent.guardrails import detect_message_language
from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import (
    CountryCode,
    LLMMessage,
    LLMRequest,
    SearchIntent,
    SessionTurn,
    StoreFilter,
    TurnAction,
)
from commerce_ai.domain.ports import LLMClient

_DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٬٫", "01234567890123456789,.")
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
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_CENTS = Decimal("0.01")

_AR_BOUNDARY_L = r"(?<![\u0621-\u064A])"
_AR_BOUNDARY_R = r"(?![\u0621-\u064A])"

_COMPARE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:compare|comparison|vs|versus|difference\s+between"
        r"|which\s+(?:one\s+)?is\s+better)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_AR_BOUNDARY_L}(?:قارن|مقارنه|الفرق\s+بين|ايهما\s+افضل|انهي\s+احسن|مين\s+احسن){_AR_BOUNDARY_R}"
    ),
)

_OFF_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:weather|forecast|temperature\s+outside|politics|election|president"
        r"|write\s+(?:python|code|poem|story|essay)|solve\s+equation|tell\s+me\s+a\s+joke"
        r"|recipe|how\s+to\s+cook|diagnose|medical\s+advice|match\s+score)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_AR_BOUNDARY_L}(?:الطقس|درجه\s+الحراره|حاله\s+الجو|السياسه|الانتخابات"
        r"|اكتب\s+(?:لي\s+)?(?:كود|بايثون|قصيده|شعر|قصه)|احكي\s+نكته"
        rf"|وصفه\s+طبخ|طريقه\s+عمل\s+(?:الكيك|الاكل)|تشخيص\s+مرض|نتيجه\s+المباراه){_AR_BOUNDARY_R}"
    ),
)

_COUNTRY_PATTERNS: tuple[tuple[CountryCode, re.Pattern[str]], ...] = (
    (
        CountryCode.SA,
        re.compile(
            r"\b(?:sa|ksa|saudi(?:\s+arabia)?|riyadh|jeddah|sar)\b"
            rf"|{_AR_BOUNDARY_L}(?:ب|ل|و|لل)?"
            rf"(?:السعوديه|سعوديه|سعودي|الرياض|رياض|جده|ريال|ر\.س){_AR_BOUNDARY_R}",
            re.IGNORECASE,
        ),
    ),
    (
        CountryCode.AE,
        re.compile(
            r"\b(?:ae|uae|emirates|dubai|abu\s+dhabi|aed)\b"
            rf"|{_AR_BOUNDARY_L}(?:ب|ل|و|لل)?"
            rf"(?:الامارات|امارات|دبي|ابوظبي|درهم|د\.ا){_AR_BOUNDARY_R}",
            re.IGNORECASE,
        ),
    ),
    (
        CountryCode.EG,
        re.compile(
            r"\b(?:eg|egypt|cairo|alexandria|egp)\b"
            rf"|{_AR_BOUNDARY_L}(?:ب|ل|و|لل)?"
            rf"(?:مصر|مصريه|مصري|القاهره|قاهره|الاسكندريه|اسكندريه|جنيه|ج\.م|جم){_AR_BOUNDARY_R}",
            re.IGNORECASE,
        ),
    ),
)

_NOON_RE = re.compile(
    r"\bnoon\b|(?<![\u0621-\u064A])(?:ب|ل|و)?نون(?![\u0621-\u064A])",
    re.IGNORECASE,
)
_AMAZON_RE = re.compile(
    r"\bamazon\b|(?<![\u0621-\u064A])(?:ب|ل|و)?امازون(?![\u0621-\u064A])",
    re.IGNORECASE,
)
_BOTH_STORES_RE = re.compile(
    r"\b(?:both\s+stores|both|all\s+stores)\b|(?:المتجرين|الاتنين|الاثنين|نون\s+وامازون)",
    re.IGNORECASE,
)

_BUDGET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:تحت(?:\s+سعر)?|اقل\s+من|بحد\s+اقصي|حد\s+اقصي|ميزانيه|ميزانيتي"
        r"|في\s+حدود|مش\s+اكتر\s+من|لا\s+يتعدي|بسعر(?:\s+اقل\s+من)?)\s*"
        r"(\d[\d,]*(?:\.\d+)?)\s*(?:جنيه|ج\.م|جم|ريال|ر\.س|درهم|د\.ا|egp|sar|aed)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\bunder\b|\bbelow\b|\bmax(?:imum)?\b|\bbudget(?:\s+of)?\b|\bup\s+to\b"
        r"|\bless\s+than\b|\bwithin\b)\s*(?:egp|sar|aed)?\s*(\d[\d,]*(?:\.\d+)?)"
        r"\s*(?:egp|sar|aed)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:بـ?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(?:جنيه|ج\.م|ريال|درهم|\begp\b|\bsar\b|\baed\b)",
        re.IGNORECASE,
    ),
)
_CLEAR_BUDGET_RE = re.compile(
    r"\b(?:unlimited\s+budget|any\s+price|no\s+budget)\b|(?:بدون\s+ميزانيه|اي\s+سعر)",
    re.IGNORECASE,
)

_RATING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:تقييم(?:ه|ات)?)\s*(?:فوق|اعلي\s+من|اكتر\s+من|علي\s+الاقل|لا\s+يقل\s+عن|من)?\s*"
        r"([0-5](?:\.\d+)?)\s*\+?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:rating|rated|min\s+rating)\s*(?:>=|above|over|at\s+least|min(?:imum)?)?\s*"
        r"([0-5](?:\.\d+)?)\s*\+?",
        re.IGNORECASE,
    ),
    re.compile(r"([0-5](?:\.\d+)?)\s*(?:\+|نجوم|نجمه|\bstars?\b)", re.IGNORECASE),
)

_ACCESSORY_RE = re.compile(
    r"\b(?:case|cases|cover|covers|charger|chargers|cable|cables|cord|cords"
    r"|adapter|adapters|protector|protectors|strap|straps|holder|holders"
    r"|mount|mounts|sleeve|sleeves|skin|skins|accessor(?:y|ies))\b"
    rf"|{_AR_BOUNDARY_L}(?:ال)?(?:جراب(?:ات)?|كفر(?:ات)?|حافظ(?:ه|ات)|شاحن|شواحن"
    r"|وصل(?:ه|ات)|كابل(?:ات)?|سلك|اسلاك|اسكرين(?:ه|ات)?|حمايه\s+شاشه"
    rf"|سوار|استراب|حامل|اكسسوار(?:ات)?){_AR_BOUNDARY_R}",
    re.IGNORECASE,
)

_GENERIC_FILLER_RE = re.compile(
    r"\b(?:hi|hello|hey|help|recommend|suggest|find|search|buy|looking\s+for|want\s+to\s+buy"
    r"|show\s+me|please|best|cheapest|cheaper|good|something|product|item|products|items"
    r"|only|from|in|on|switch\s+to|change\s+to|with|accessories|include)\b"
    r"|(?<![\u0621-\u064A])(?:السلام\s+عليكم|مرحبا|اهلا|ازيك|مساعده|عايز|عاوز"
    r"|ابحث(?:\s+لي)?(?:\s+عن)?|رشح(?:\s+لي)?|اقترح|هات|دور\s+علي|اشتري"
    r"|حاج[هة]|منتج(?:ات)?|افضل|احسن|ارخص|كويس[هة]?|فقط|بس|من|في|علي"
    r"|بدل(?:\s+ل)?|غير(?:\s+ل)?|مع|شامل|الاكسسوارات|لو\s+سمحت)(?![\u0621-\u064A])",
    re.IGNORECASE,
)
_CLEAN_COUNTRY_STRIP_RE = re.compile(
    r"\b(?:sa|ksa|saudi(?:\s+arabia)?|riyadh|jeddah|sar|ae|uae|emirates|dubai|abu\s+dhabi"
    r"|aed|eg|egypt|cairo|alexandria|egp)\b"
    r"|(?<![\u0621-\u064A])(?:ب|ل|و|لل)?(?:السعوديه|سعوديه|سعودي|الرياض|رياض|جده"
    r"|الامارات|امارات|دبي|ابوظبي|مصر|مصريه|مصري|القاهره|قاهره|الاسكندريه|اسكندريه)(?![\u0621-\u064A])",
    re.IGNORECASE,
)
_CLEAN_STORE_STRIP_RE = re.compile(
    r"\b(?:noon|amazon|both\s+stores|both|all\s+stores)\b"
    r"|(?<![\u0621-\u064A])(?:ب|ل|و)?(?:نون|امازون|المتجرين|الاثنين|الاتنين)(?![\u0621-\u064A])",
    re.IGNORECASE,
)
_QUERY_CLEANUP_PUNCT_RE = re.compile(r"[\s,!؟?.;:()\[\]{}\"'`~]+")

_SYSTEM_PROMPT = (
    "You are an e-commerce intent parser for Egypt (EG), Saudi Arabia (SA), and UAE (AE) "
    "across Noon and Amazon. Convert Arabic-Indic numerals to ASCII digits. "
    "Return ONLY valid JSON with keys: "
    '"action" ("search"|"compare"|"clarify"|"off_topic"), '
    '"query" (string|null, core product name only without price/store/country words), '
    '"country" ("EG"|"SA"|"AE"|null), '
    '"store" ("noon"|"amazon"|"both"|null), '
    '"max_budget" (number|null), '
    '"min_rating" (number|null), '
    '"exclude_keywords" (string[]), '
    '"include_accessories" (boolean|null), '
    '"is_new_product" (boolean), '
    '"language" ("ar"|"en"), '
    '"clarification_question" (string|null). '
    "Set is_new_product=true when switching to a brand-new product vs prior_intent; "
    "false when refining budget, store, country, or rating on the prior product."
)


class IntentExtractionResult(BaseModel):
    """Structured result of bilingual intent classification and SearchIntent extraction."""

    model_config = ConfigDict(extra="forbid")

    action: TurnAction
    intent: SearchIntent | None = None
    language: Literal["ar", "en"] = "ar"
    clarification_question: str | None = None
    used_rule_fallback: bool = False
    llm_calls_used: int = Field(default=0, ge=0, le=1)
    degraded_reason: str | None = None


class _LLMIntentPayload(BaseModel):
    """Strict validator for LLM Call #1 JSON output."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["search", "compare", "clarify", "off_topic"]
    query: str | None = None
    country: CountryCode | None = None
    store: StoreFilter | None = None
    max_budget: Decimal | None = None
    min_rating: float | None = Field(default=None, ge=0.0, le=5.0, allow_inf_nan=False)
    exclude_keywords: tuple[str, ...] = ()
    include_accessories: bool | None = None
    is_new_product: bool = False
    language: Literal["ar", "en"] | None = None
    clarification_question: str | None = None


def _normalize_digits_and_arabic(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text).translate(_DIGIT_TRANS)
    without_diacritics = _ARABIC_DIACRITICS_RE.sub("", nfkc)
    return without_diacritics.translate(_ARABIC_ORTHOGRAPHY_TRANS)


def _query_topic_tokens(query: str) -> set[str]:
    norm = _normalize_digits_and_arabic(query).lower()
    cleaned = _QUERY_CLEANUP_PUNCT_RE.sub(" ", norm)
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def _is_same_product_topic(new_query: str, prior_query: str) -> bool:
    new_tokens = _query_topic_tokens(new_query)
    prior_tokens = _query_topic_tokens(prior_query)
    if not new_tokens or not prior_tokens:
        return True
    return bool(new_tokens & prior_tokens)


def _localized_clarification(language: Literal["ar", "en"]) -> str:
    if language == "en":
        return (
            "Which specific product or category are you looking for "
            "(for example: Anker earbuds, iPhone 15, or an air fryer)?"
        )
    return "ما المنتج أو الفئة التي تبحث عنها تحديداً (مثل: سماعات أنكر، آيفون 15، قلاية هوائية)؟"


def _strip_markdown_fences(raw: str) -> str:
    stripped = raw.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_country(folded_text: str) -> CountryCode | None:
    for country, pattern in _COUNTRY_PATTERNS:
        if pattern.search(folded_text):
            return country
    return None


def _extract_store(folded_text: str) -> StoreFilter | None:
    if _BOTH_STORES_RE.search(folded_text):
        return StoreFilter.BOTH
    has_noon = _NOON_RE.search(folded_text) is not None
    has_amazon = _AMAZON_RE.search(folded_text) is not None
    if has_noon and has_amazon:
        return StoreFilter.BOTH
    if has_noon:
        return StoreFilter.NOON
    if has_amazon:
        return StoreFilter.AMAZON
    return None


def _extract_budget(folded_text: str) -> tuple[Decimal | None, bool, str]:
    """Return (budget_value, explicitly_cleared, text_without_budget_span)."""
    if _CLEAR_BUDGET_RE.search(folded_text):
        cleaned = _CLEAR_BUDGET_RE.sub(" ", folded_text)
        return None, True, cleaned

    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(folded_text)
        if match:
            raw_num = match.group(1).replace(",", "")
            try:
                value = Decimal(raw_num).quantize(_CENTS, rounding=ROUND_HALF_UP)
            except InvalidOperation:
                continue
            if value > Decimal("0.00"):
                cleaned = f"{folded_text[: match.start()]} {folded_text[match.end() :]}"
                return value, False, cleaned
    return None, False, folded_text


def _extract_rating(folded_text: str) -> tuple[float | None, str]:
    for pattern in _RATING_PATTERNS:
        match = pattern.search(folded_text)
        if match:
            try:
                rating = float(match.group(1))
            except ValueError:
                continue
            if math.isfinite(rating) and 0.0 <= rating <= 5.0:
                cleaned = f"{folded_text[: match.start()]} {folded_text[match.end() :]}"
                return rating, cleaned
    return None, folded_text


def _clean_product_query(raw_remainder: str, original_message: str) -> str:
    """Clean extracted query while preserving readable product casing from original text."""
    working = raw_remainder
    working = _CLEAN_COUNTRY_STRIP_RE.sub(" ", working)
    working = _CLEAN_STORE_STRIP_RE.sub(" ", working)
    working = _GENERIC_FILLER_RE.sub(" ", working)
    working = _QUERY_CLEANUP_PUNCT_RE.sub(" ", working).strip()
    if not working:
        return ""
    if working.isascii():
        orig_ascii = _QUERY_CLEANUP_PUNCT_RE.sub(" ", original_message).strip()
        orig_words = orig_ascii.split()
        target_tokens = working.lower().split()
        preserved: list[str] = []
        idx = 0
        for tok in target_tokens:
            while idx < len(orig_words) and orig_words[idx].lower() != tok:
                idx += 1
            if idx < len(orig_words):
                preserved.append(orig_words[idx])
                idx += 1
            else:
                preserved.append(tok)
        return " ".join(preserved)
    return working


def _apply_overrides(
    intent: SearchIntent | None,
    *,
    store_override: StoreFilter | None,
    max_budget_override: Decimal | None,
    language: Literal["ar", "en"] | None = None,
) -> SearchIntent | None:
    if intent is None:
        return None
    updates: dict[str, Any] = {}
    if language is not None:
        updates["language"] = language
    if store_override is not None:
        updates["store"] = store_override
    if max_budget_override is not None:
        updates["max_budget"] = max_budget_override
    if not updates:
        return intent
    return intent.model_copy(update=updates)


def _parse_with_rules(
    message: str,
    *,
    default_country: CountryCode,
    store_override: StoreFilter | None,
    max_budget_override: Decimal | None,
    language_hint: Literal["ar", "en"] | None,
    prior_intent: SearchIntent | None,
    degraded_reason: str | None,
    llm_calls_used: int,
) -> IntentExtractionResult:
    language: Literal["ar", "en"] = language_hint or detect_message_language(message)
    folded = _normalize_digits_and_arabic(message)

    # 1. Compare turn
    if any(pattern.search(folded) for pattern in _COMPARE_PATTERNS):
        intent = _apply_overrides(
            prior_intent,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language=language_hint,
        )
        return IntentExtractionResult(
            action=TurnAction.COMPARE,
            intent=intent,
            language=language,
            used_rule_fallback=True,
            llm_calls_used=llm_calls_used,
            degraded_reason=degraded_reason,
        )

    # Extract structured constraints before checking off-topic / clarify
    detected_country = _extract_country(folded)
    detected_store = _extract_store(folded)
    detected_budget, budget_cleared, remainder = _extract_budget(folded)
    detected_rating, remainder = _extract_rating(remainder)
    has_accessory_term = _ACCESSORY_RE.search(folded) is not None
    cleaned_query = _clean_product_query(remainder, message)

    has_refinement_constraint = any(
        (
            detected_country is not None,
            detected_store is not None,
            detected_budget is not None,
            budget_cleared,
            detected_rating is not None,
        )
    )

    # 2. Off-topic check (only when no product query or refinement signals exist)
    if not has_refinement_constraint and any(
        pattern.search(folded) for pattern in _OFF_TOPIC_PATTERNS
    ):
        return IntentExtractionResult(
            action=TurnAction.OFF_TOPIC,
            intent=None,
            language=language,
            used_rule_fallback=True,
            llm_calls_used=llm_calls_used,
            degraded_reason=degraded_reason,
        )

    # 3. Search vs Refinement vs Clarify
    if cleaned_query:
        is_same_topic = prior_intent is not None and _is_same_product_topic(
            cleaned_query, prior_intent.query
        )
        if is_same_topic and prior_intent is not None:
            country = detected_country or prior_intent.country
            store = detected_store or prior_intent.store
            max_budget = (
                None
                if budget_cleared
                else (detected_budget if detected_budget is not None else prior_intent.max_budget)
            )
            min_rating = detected_rating if detected_rating is not None else prior_intent.min_rating
            include_acc = has_accessory_term or prior_intent.include_accessories
            exclude_kw = prior_intent.exclude_keywords
        else:
            # New product topic clears stale prior max_budget / min_rating / exclude_keywords.
            country = detected_country or (
                prior_intent.country if prior_intent is not None else default_country
            )
            store = detected_store or StoreFilter.BOTH
            max_budget = detected_budget
            min_rating = detected_rating
            include_acc = has_accessory_term
            exclude_kw = ()

        intent = SearchIntent(
            query=cleaned_query,
            country=country,
            store=store,
            max_budget=max_budget,
            min_rating=min_rating,
            exclude_keywords=exclude_kw,
            include_accessories=include_acc,
            language=language,
        )
        intent = _apply_overrides(
            intent,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language=language,
        )
        return IntentExtractionResult(
            action=TurnAction.SEARCH,
            intent=intent,
            language=language,
            used_rule_fallback=True,
            llm_calls_used=llm_calls_used,
            degraded_reason=degraded_reason,
        )

    if prior_intent is not None and has_refinement_constraint:
        max_budget = (
            None
            if budget_cleared
            else (detected_budget if detected_budget is not None else prior_intent.max_budget)
        )
        intent = SearchIntent(
            query=prior_intent.query,
            country=detected_country or prior_intent.country,
            store=detected_store or prior_intent.store,
            max_budget=max_budget,
            min_rating=(
                detected_rating if detected_rating is not None else prior_intent.min_rating
            ),
            exclude_keywords=prior_intent.exclude_keywords,
            include_accessories=has_accessory_term or prior_intent.include_accessories,
            language=language,
        )
        intent = _apply_overrides(
            intent,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language=language,
        )
        return IntentExtractionResult(
            action=TurnAction.SEARCH,
            intent=intent,
            language=language,
            used_rule_fallback=True,
            llm_calls_used=llm_calls_used,
            degraded_reason=degraded_reason,
        )

    # 4. Underspecified query -> CLARIFY
    return IntentExtractionResult(
        action=TurnAction.CLARIFY,
        intent=None,
        language=language,
        clarification_question=_localized_clarification(language),
        used_rule_fallback=True,
        llm_calls_used=llm_calls_used,
        degraded_reason=degraded_reason,
    )


def _build_intent_llm_request(
    message: str,
    *,
    default_country: CountryCode,
    store_override: StoreFilter | None,
    max_budget_override: Decimal | None,
    language_hint: Literal["ar", "en"] | None,
    prior_intent: SearchIntent | None,
    recent_turns: Sequence[SessionTurn],
    has_saved_offers: bool,
) -> LLMRequest:
    compact_history = [
        {"role": turn.role, "content": turn.content[:200], "action": turn.action}
        for turn in recent_turns[-6:]
    ]
    user_payload = {
        "message": message,
        "default_country": default_country.value,
        "prior_intent": prior_intent.model_dump(mode="json") if prior_intent else None,
        "recent_turns": compact_history,
        "has_saved_offers": has_saved_offers,
        "overrides": {
            "store_override": store_override.value if store_override else None,
            "max_budget_override": str(max_budget_override) if max_budget_override else None,
            "language_hint": language_hint,
        },
    }
    return LLMRequest(
        messages=(
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
        ),
        max_tokens=350,
        temperature=0.0,
        json_mode=True,
        task_name="intent_extraction",
    )


def _merge_llm_search_intent(
    payload: _LLMIntentPayload,
    *,
    default_country: CountryCode,
    prior_intent: SearchIntent | None,
    language: Literal["ar", "en"],
) -> SearchIntent | None:
    raw_query = payload.query.strip() if payload.query is not None else ""
    if not raw_query and prior_intent is None:
        return None

    if not raw_query and prior_intent is not None:
        # Pure follow-up refinement inheriting prior_intent fields unless overridden in payload.
        query = prior_intent.query
        is_new_product = False
    else:
        query = raw_query
        if prior_intent is None:
            is_new_product = True
        else:
            is_new_product = payload.is_new_product or not _is_same_product_topic(
                query, prior_intent.query
            )

    if is_new_product or prior_intent is None:
        country = payload.country or (
            prior_intent.country if prior_intent is not None else default_country
        )
        store = payload.store or StoreFilter.BOTH
        max_budget = payload.max_budget
        min_rating = payload.min_rating
        exclude_keywords = tuple(k.strip() for k in payload.exclude_keywords if k.strip())
        include_accessories = bool(payload.include_accessories)
    else:
        country = payload.country or prior_intent.country
        store = payload.store or prior_intent.store
        max_budget = (
            payload.max_budget if payload.max_budget is not None else prior_intent.max_budget
        )
        min_rating = (
            payload.min_rating if payload.min_rating is not None else prior_intent.min_rating
        )
        exclude_keywords = (
            tuple(k.strip() for k in payload.exclude_keywords if k.strip())
            if payload.exclude_keywords
            else prior_intent.exclude_keywords
        )
        include_accessories = (
            payload.include_accessories
            if payload.include_accessories is not None
            else prior_intent.include_accessories
        )

    return SearchIntent(
        query=query,
        country=country,
        store=store,
        max_budget=max_budget,
        min_rating=min_rating,
        exclude_keywords=exclude_keywords,
        include_accessories=include_accessories,
        language=language,
    )


async def extract_turn_intent(
    message: str,
    *,
    default_country: CountryCode,
    store_override: StoreFilter | None = None,
    max_budget_override: Decimal | None = None,
    language_hint: Literal["ar", "en"] | None = None,
    prior_intent: SearchIntent | None = None,
    recent_turns: Sequence[SessionTurn] = (),
    has_saved_offers: bool = False,
    llm_client: LLMClient | None = None,
) -> IntentExtractionResult:
    """Classify turn action and extract validated SearchIntent (Call #1 or rule fallback)."""
    if llm_client is None:
        return _parse_with_rules(
            message,
            default_country=default_country,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language_hint=language_hint,
            prior_intent=prior_intent,
            degraded_reason=None,
            llm_calls_used=0,
        )

    request = _build_intent_llm_request(
        message,
        default_country=default_country,
        store_override=store_override,
        max_budget_override=max_budget_override,
        language_hint=language_hint,
        prior_intent=prior_intent,
        recent_turns=recent_turns,
        has_saved_offers=has_saved_offers,
    )

    try:
        response = await llm_client.complete(request)
    except LLMProviderError as exc:
        return _parse_with_rules(
            message,
            default_country=default_country,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language_hint=language_hint,
            prior_intent=prior_intent,
            degraded_reason=f"llm_provider_error:{exc.provider}",
            llm_calls_used=1,
        )

    cleaned_json = _strip_markdown_fences(response.content)
    try:
        raw_obj: Any = json.loads(cleaned_json)
        if not isinstance(raw_obj, dict):
            raise ValueError("LLM intent payload must be a JSON object")
        payload = _LLMIntentPayload.model_validate(raw_obj)
    except (ValueError, ValidationError):
        return _parse_with_rules(
            message,
            default_country=default_country,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language_hint=language_hint,
            prior_intent=prior_intent,
            degraded_reason="llm_invalid_intent_json",
            llm_calls_used=1,
        )

    detected_lang = detect_message_language(message)
    final_language: Literal["ar", "en"] = language_hint or payload.language or detected_lang
    action = TurnAction(payload.action)

    if action == TurnAction.SEARCH:
        try:
            merged_intent = _merge_llm_search_intent(
                payload,
                default_country=default_country,
                prior_intent=prior_intent,
                language=final_language,
            )
        except ValidationError:
            return _parse_with_rules(
                message,
                default_country=default_country,
                store_override=store_override,
                max_budget_override=max_budget_override,
                language_hint=language_hint,
                prior_intent=prior_intent,
                degraded_reason="llm_invalid_search_intent",
                llm_calls_used=1,
            )

        if merged_intent is None:
            return _parse_with_rules(
                message,
                default_country=default_country,
                store_override=store_override,
                max_budget_override=max_budget_override,
                language_hint=language_hint,
                prior_intent=prior_intent,
                degraded_reason="llm_missing_search_query",
                llm_calls_used=1,
            )

        final_intent = _apply_overrides(
            merged_intent,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language=final_language,
        )
        return IntentExtractionResult(
            action=TurnAction.SEARCH,
            intent=final_intent,
            language=final_language,
            used_rule_fallback=False,
            llm_calls_used=1,
        )

    if action == TurnAction.COMPARE:
        compare_intent = _apply_overrides(
            prior_intent,
            store_override=store_override,
            max_budget_override=max_budget_override,
            language=language_hint,
        )
        return IntentExtractionResult(
            action=TurnAction.COMPARE,
            intent=compare_intent,
            language=final_language,
            used_rule_fallback=False,
            llm_calls_used=1,
        )

    if action == TurnAction.CLARIFY:
        question = (
            payload.clarification_question.strip()
            if payload.clarification_question and payload.clarification_question.strip()
            else _localized_clarification(final_language)
        )
        return IntentExtractionResult(
            action=TurnAction.CLARIFY,
            intent=None,
            language=final_language,
            clarification_question=question,
            used_rule_fallback=False,
            llm_calls_used=1,
        )

    return IntentExtractionResult(
        action=TurnAction.OFF_TOPIC,
        intent=None,
        language=final_language,
        used_rule_fallback=False,
        llm_calls_used=1,
    )
