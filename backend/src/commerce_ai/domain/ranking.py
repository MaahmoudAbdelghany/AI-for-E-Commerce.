"""Pure deterministic Top-K value scoring, bilingual anti-accessory filtering, and outlier guard."""

import re
import statistics
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

from commerce_ai.config import ScoringConfig
from commerce_ai.domain.models import (
    ProductOffer,
    RankedOffer,
    RankingResult,
    SearchIntent,
    StoreFilter,
)

_ZERO = Decimal("0")
_MAX_RANKED_CAP = 3
_WORD_BOUNDARY_LEFT = r"(?<![^\W_])"
_WORD_BOUNDARY_RIGHT = r"(?![^\W_])"

_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064A]")
_ARABIC_CHAR_TRANS = str.maketrans(
    {
        "\u0622": "\u0627",  # آ -> ا
        "\u0623": "\u0627",  # أ -> ا
        "\u0625": "\u0627",  # إ -> ا
        "\u0671": "\u0627",  # ٱ -> ا
        "\u0629": "\u0647",  # ة -> ه
        "\u0649": "\u064a",  # ى -> ي
        "_": " ",
    }
)

_ACCESSORY_PATTERN_BODIES: tuple[str, ...] = (
    # English accessory keywords (word-boundary + optional plural 's')
    "cases?",
    "covers?",
    "protectors?",
    "cables?",
    "cords?",
    "chargers?",
    "adapters?",
    "straps?",
    "holders?",
    "mounts?",
    "skins?",
    "sleeves?",
    # Arabic accessory keywords (normalized forms with optional 'ال' prefix)
    r"(?:ال)?جراب(?:ات)?",
    r"(?:ال)?كفر(?:ات)?",
    r"(?:ال)?حافظ(?:ه|ات)",
    r"(?:ال)?(?:شاحن|شواحن)",
    r"(?:ال)?اسكرين(?:ه|ات)?",
    r"(?:ال)?حمايه\s+(?:ال)?شاشه",
    r"(?:ال)?وصل(?:ه|ات)",
    r"(?:ال)?كابل(?:ات)?",
    r"(?:ال)?(?:سلك|اسلاك)",
    r"(?:ال)?حامل",
    r"(?:ال)?سوار",
)

_ACCESSORY_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{body}\b") for body in _ACCESSORY_PATTERN_BODIES
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """Internal offer wrapper pairing an immutable ProductOffer with its normalized title."""

    offer: ProductOffer
    normalized_title: str


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    """Internal scored candidate prior to sorting and match-reason attribution."""

    offer: ProductOffer
    value_score: float
    price_norm: float
    bayesian_rating: float
    is_unrated_fallback: bool


def _normalize_text(text: str) -> str:
    """Normalize English case and Arabic diacritics/orthographic variants."""
    if text.isascii():
        return " ".join(text.lower().replace("_", " ").split())
    normalized = unicodedata.normalize("NFKC", text).casefold()
    without_diacritics = _ARABIC_DIACRITICS_RE.sub("", normalized)
    translated = without_diacritics.translate(_ARABIC_CHAR_TRANS)
    return " ".join(translated.split())


@lru_cache(maxsize=64)
def _get_disallowed_accessories_regex(
    disallowed_mask: tuple[bool, ...],
) -> re.Pattern[str] | None:
    """Compile and cache a single combined boundary-aware regex for disallowed accessories."""
    bodies = [
        body
        for body, disallowed in zip(_ACCESSORY_PATTERN_BODIES, disallowed_mask, strict=True)
        if disallowed
    ]
    if not bodies:
        return None
    return re.compile(rf"\b(?:{'|'.join(bodies)})\b")


def _compile_exclude_patterns(exclude_keywords: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile boundary-aware regex patterns for normalized user exclude keywords."""
    patterns: list[re.Pattern[str]] = []
    for raw_kw in exclude_keywords:
        norm_kw = _normalize_text(raw_kw)
        if not norm_kw:
            continue
        token_parts: list[str] = []
        for token in norm_kw.split():
            if _ARABIC_LETTER_RE.search(token):
                core = token[2:] if token.startswith("ال") and len(token) > 2 else token
                suffix = "ه?" if not core.endswith("ه") else ""
                token_parts.append(f"(?:ال)?{re.escape(core)}{suffix}")
            else:
                token_parts.append(re.escape(token))
        joined = r"\s+".join(token_parts)
        patterns.append(re.compile(f"{_WORD_BOUNDARY_LEFT}{joined}{_WORD_BOUNDARY_RIGHT}"))
    return tuple(patterns)


def _passes_hard_filters(
    offer: ProductOffer,
    normalized_title: str,
    intent: SearchIntent,
    exclude_patterns: tuple[re.Pattern[str], ...],
) -> bool:
    """Apply hard eligibility constraints prior to Stage 1/2 filtering."""
    if not offer.in_stock:
        return False
    if offer.price <= _ZERO:
        return False
    if offer.country != intent.country:
        return False
    if intent.store != StoreFilter.BOTH and offer.store.value != intent.store.value:
        return False
    if intent.max_budget is not None and offer.price > intent.max_budget:
        return False
    if intent.min_rating is not None and (
        offer.rating is None or offer.review_count <= 0 or offer.rating < intent.min_rating
    ):
        return False
    return not any(pattern.search(normalized_title) for pattern in exclude_patterns)


def _filter_stage1_accessories(
    candidates: Sequence[_Candidate],
    normalized_query: str,
    *,
    include_accessories: bool,
) -> tuple[list[_Candidate], int]:
    """Run Stage 1 intent-aware bilingual anti-accessory filter (P4)."""
    if include_accessories:
        return list(candidates), 0

    disallowed_mask = tuple(
        pattern.search(normalized_query) is None for pattern in _ACCESSORY_QUERY_PATTERNS
    )
    disallowed_regex = _get_disallowed_accessories_regex(disallowed_mask)
    if disallowed_regex is None:
        return list(candidates), 0

    surviving: list[_Candidate] = []
    filtered_count = 0
    for candidate in candidates:
        if disallowed_regex.search(candidate.normalized_title) is not None:
            filtered_count += 1
        else:
            surviving.append(candidate)
    return surviving, filtered_count


def _filter_stage2_outliers(
    candidates: Sequence[_Candidate],
    intent: SearchIntent,
    config: ScoringConfig,
) -> tuple[list[_Candidate], int]:
    """Run Stage 2 statistical median price floor & upper anomaly guard (P4)."""
    if len(candidates) < config.min_candidates_for_outlier_guard:
        return list(candidates), 0

    median_price: Decimal = statistics.median([candidate.offer.price for candidate in candidates])
    floor_threshold = Decimal(str(config.price_floor_ratio)) * median_price
    ceiling_threshold = Decimal(str(config.price_ceiling_ratio)) * median_price
    enforce_upper_ceiling = intent.max_budget is None

    surviving: list[_Candidate] = []
    filtered_count = 0
    for candidate in candidates:
        price = candidate.offer.price
        if price < floor_threshold or (enforce_upper_ceiling and price > ceiling_threshold):
            filtered_count += 1
        else:
            surviving.append(candidate)
    return surviving, filtered_count


def _score_and_rank(
    candidates: Sequence[_Candidate],
    intent: SearchIntent,
    config: ScoringConfig,
) -> list[RankedOffer]:
    """Compute Bayesian ratings, price normalization, composite value scores, and match reasons."""
    if not candidates:
        return []

    p_min = min(candidate.offer.price for candidate in candidates)
    p_max = max(candidate.offer.price for candidate in candidates)
    price_span = p_max - p_min
    m = float(config.bayesian_prior_count)
    prior_mean = config.bayesian_prior_mean

    scored: list[_ScoredCandidate] = []
    for candidate in candidates:
        offer = candidate.offer
        if offer.rating is None or offer.review_count == 0:
            raw_bayesian = config.unrated_prior_rating
            is_unrated = True
        else:
            v = float(offer.review_count)
            raw_bayesian = (v / (v + m)) * offer.rating + (m / (v + m)) * prior_mean
            is_unrated = False

        raw_price_norm = 1.0 if price_span == _ZERO else float((p_max - offer.price) / price_span)

        clamped_price_norm = min(1.0, max(0.0, raw_price_norm))
        clamped_bayesian = min(5.0, max(0.0, raw_bayesian))
        r_norm = clamped_bayesian / 5.0
        raw_value_score = 100.0 * (
            config.price_weight * clamped_price_norm + config.rating_weight * r_norm
        )

        scored.append(
            _ScoredCandidate(
                offer=offer,
                value_score=round(min(100.0, max(0.0, raw_value_score)), 2),
                price_norm=round(clamped_price_norm, 4),
                bayesian_rating=round(clamped_bayesian, 4),
                is_unrated_fallback=is_unrated,
            )
        )

    scored.sort(
        key=lambda item: (
            -item.value_score,
            -item.offer.review_count,
            item.offer.price,
            item.offer.offer_id,
        )
    )

    rated_scores = [item.bayesian_rating for item in scored if not item.is_unrated_fallback]
    max_rated_bayesian: float | None = max(rated_scores) if rated_scores else None
    effective_top_k = min(config.top_k, _MAX_RANKED_CAP)

    ranked_offers: list[RankedOffer] = []
    for rank, item in enumerate(scored[:effective_top_k], start=1):
        reasons: list[str] = []
        if rank == 1:
            reasons.append("best_overall_value")
        if item.offer.price == p_min:
            reasons.append("lowest_price")
        if (
            not item.is_unrated_fallback
            and max_rated_bayesian is not None
            and item.bayesian_rating == max_rated_bayesian
        ):
            reasons.append("top_bayesian_rating")
        if not item.is_unrated_fallback and item.offer.review_count >= config.bayesian_prior_count:
            reasons.append("high_review_confidence")
        if intent.max_budget is not None:
            reasons.append("within_budget")
        if item.is_unrated_fallback:
            reasons.append("unrated_fallback")
        if not reasons:
            reasons.append("strong_value_runner_up")

        ranked_offers.append(
            RankedOffer(
                rank=rank,
                offer=item.offer,
                value_score=item.value_score,
                price_norm=item.price_norm,
                bayesian_rating=item.bayesian_rating,
                match_reasons=tuple(reasons),
            )
        )

    return ranked_offers


def rank_top_offers(
    offers: Sequence[ProductOffer],
    intent: SearchIntent,
    config: ScoringConfig | None = None,
) -> RankingResult:
    """Filter, guard, score, and return Top-K verified marketplace offers deterministically."""
    active_config = config if config is not None else ScoringConfig()
    total_candidates = len(offers)
    if total_candidates == 0:
        return RankingResult(
            ranked_offers=[],
            total_candidates=0,
            filtered_accessories_count=0,
            filtered_outliers_count=0,
            degraded_fewer_than_k=True,
        )

    exclude_patterns = _compile_exclude_patterns(intent.exclude_keywords)
    eligible: list[_Candidate] = []
    for offer in offers:
        norm_title = _normalize_text(offer.title)
        if _passes_hard_filters(offer, norm_title, intent, exclude_patterns):
            eligible.append(_Candidate(offer=offer, normalized_title=norm_title))

    normalized_query = _normalize_text(intent.query)
    post_stage1, filtered_accessories_count = _filter_stage1_accessories(
        eligible,
        normalized_query,
        include_accessories=intent.include_accessories,
    )
    post_stage2, filtered_outliers_count = _filter_stage2_outliers(
        post_stage1,
        intent,
        active_config,
    )

    ranked_offers = _score_and_rank(post_stage2, intent, active_config)
    return RankingResult(
        ranked_offers=ranked_offers,
        total_candidates=total_candidates,
        filtered_accessories_count=filtered_accessories_count,
        filtered_outliers_count=filtered_outliers_count,
        degraded_fewer_than_k=len(ranked_offers) < active_config.top_k,
    )
