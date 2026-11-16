"""Zero-token deterministic bilingual (ar/en) templates for grounded responses."""

from collections.abc import Sequence
from typing import Literal

from commerce_ai.domain.models import RankedOffer, SearchIntent, StoreId

_STORE_LABELS_AR: dict[StoreId, str] = {
    StoreId.NOON: "نون",
    StoreId.AMAZON: "أمازون",
}
_STORE_LABELS_EN: dict[StoreId, str] = {
    StoreId.NOON: "Noon",
    StoreId.AMAZON: "Amazon",
}

_REASON_LABELS_AR: dict[str, str] = {
    "best_overall_value": "أفضل قيمة إجمالية",
    "lowest_price": "أقل سعر",
    "top_bayesian_rating": "أعلى تقييم موثوق",
    "high_review_confidence": "عدد مراجعات قوي",
    "within_budget": "ضمن الميزانية",
    "unrated_fallback": "غير مُقيّم بعد",
    "strong_value_runner_up": "بديل قوي للقيمة",
}
_REASON_LABELS_EN: dict[str, str] = {
    "best_overall_value": "Best overall value",
    "lowest_price": "Lowest price",
    "top_bayesian_rating": "Top Bayesian rating",
    "high_review_confidence": "High review confidence",
    "within_budget": "Within budget",
    "unrated_fallback": "Unrated fallback",
    "strong_value_runner_up": "Strong runner-up",
}


def _format_rating(item: RankedOffer, language: Literal["ar", "en"]) -> str:
    offer = item.offer
    if offer.rating is None or offer.review_count == 0:
        return "غير مُقيّم (0 مراجعات)" if language == "ar" else "Unrated (0 reviews)"
    if language == "ar":
        return f"{offer.rating:.1f}/5 ({offer.review_count} مراجعة)"
    return f"{offer.rating:.1f}/5 ({offer.review_count} reviews)"


def _format_reasons(item: RankedOffer, language: Literal["ar", "en"]) -> str:
    mapping = _REASON_LABELS_AR if language == "ar" else _REASON_LABELS_EN
    labels = [mapping.get(code, code) for code in item.match_reasons]
    if not labels:
        return ""
    sep = "، " if language == "ar" else ", "
    return sep.join(labels)


def _format_offer_line(item: RankedOffer, language: Literal["ar", "en"]) -> str:
    offer = item.offer
    store_label = (
        _STORE_LABELS_AR[offer.store] if language == "ar" else _STORE_LABELS_EN[offer.store]
    )
    rating_text = _format_rating(item, language)
    reasons_text = _format_reasons(item, language)
    if language == "ar":
        reasons_part = f" | المميزات: {reasons_text}" if reasons_text else ""
        return (
            f"{item.rank}. {offer.title} — "
            f"السعر: {offer.price:.2f} {offer.currency.value} | "
            f"المتجر: {store_label} | "
            f"التقييم: {rating_text} | "
            f"نقاط القيمة: {item.value_score:.2f}/100"
            f"{reasons_part} | "
            f"الرابط: {offer.url}"
        )
    reasons_part = f" | Highlights: {reasons_text}" if reasons_text else ""
    return (
        f"{item.rank}. {offer.title} — "
        f"Price: {offer.price:.2f} {offer.currency.value} | "
        f"Store: {store_label} | "
        f"Rating: {rating_text} | "
        f"Value score: {item.value_score:.2f}/100"
        f"{reasons_part} | "
        f"Link: {offer.url}"
    )


def render_offers_summary(
    offers: Sequence[RankedOffer],
    *,
    language: Literal["ar", "en"],
    degraded_fewer_than_k: bool = False,
    intent: SearchIntent | None = None,
) -> str:
    """Render deterministic verified Top-K, partial (< top_k), or 0-offer summary."""
    if len(offers) == 0:
        if language == "ar":
            scope = f' لـ "{intent.query}"' if intent is not None else ""
            budget_hint = (
                f" ضمن ميزانية {intent.max_budget:.2f}"
                if intent is not None and intent.max_budget is not None
                else ""
            )
            return (
                f"لم يتم العثور على عروض متاحة ومطابقة{scope}{budget_hint} حالياً. "
                "جرّب رفع الميزانية أو البحث في كلا المتجرين (نون وأمازون)."
            )
        scope = f' for "{intent.query}"' if intent is not None else ""
        budget_hint = (
            f" within budget {intent.max_budget:.2f}"
            if intent is not None and intent.max_budget is not None
            else ""
        )
        return (
            f"No qualifying in-stock offers were found{scope}{budget_hint} right now. "
            "Try increasing your budget or searching across both Noon and Amazon."
        )

    if language == "ar":
        if degraded_fewer_than_k:
            header = (
                f"تم العثور على {len(offers)} عرض/عروض مطابقة وموثقة فقط "
                "(أقل من 3 عروض دون إضافة أي نتائج غير حقيقية):"
            )
        else:
            header = f"إليك أفضل {len(offers)} عروض موثقة مرتبة حسب القيمة مقابل السعر:"
    else:
        if degraded_fewer_than_k:
            header = (
                f"Only {len(offers)} qualifying verified offer(s) matched "
                "(fewer than 3, with zero fabricated results):"
            )
        else:
            header = f"Here are the top {len(offers)} verified offers ranked by overall value:"

    lines = [header, *(_format_offer_line(item, language) for item in offers)]
    return "\n".join(lines)


def render_comparison_summary(
    offers: Sequence[RankedOffer],
    *,
    language: Literal["ar", "en"],
) -> str:
    """Render deterministic side-by-side comparison of saved verified RankedOffer items."""
    if not offers:
        return render_clarification_message(
            language=language,
            missing_saved_offers_for_compare=True,
        )

    cheapest = min(offers, key=lambda item: item.offer.price)
    rated_offers = [
        item for item in offers if item.offer.rating is not None and item.offer.review_count > 0
    ]
    top_rated = max(
        rated_offers,
        key=lambda item: (item.bayesian_rating, item.offer.review_count),
        default=None,
    )
    best_value = offers[0]

    if language == "ar":
        highlights = [
            f"مقارنة بين {len(offers)} عروض محفوظة وموثقة:",
            (
                f"- الأفضل قيمة إجمالية: #{best_value.rank} ({best_value.offer.title}) "
                f"بنقاط قيمة {best_value.value_score:.2f}/100."
            ),
            (
                f"- الأقل سعراً: #{cheapest.rank} ({cheapest.offer.title}) "
                f"بسعر {cheapest.offer.price:.2f} {cheapest.offer.currency.value}."
            ),
        ]
        if top_rated is not None:
            highlights.append(
                f"- الأعلى تقييماً موثوقاً: #{top_rated.rank} ({top_rated.offer.title}) "
                f"بتقييم {top_rated.offer.rating:.1f}/5 ({top_rated.offer.review_count} مراجعة)."
            )
        details = [_format_offer_line(item, language) for item in offers]
        return "\n".join([*highlights, *details])

    highlights = [
        f"Side-by-side comparison of {len(offers)} verified saved offer(s):",
        (
            f"- Best overall value: #{best_value.rank} ({best_value.offer.title}) "
            f"with value score {best_value.value_score:.2f}/100."
        ),
        (
            f"- Lowest price: #{cheapest.rank} ({cheapest.offer.title}) "
            f"at {cheapest.offer.price:.2f} {cheapest.offer.currency.value}."
        ),
    ]
    if top_rated is not None:
        highlights.append(
            f"- Highest Bayesian rating: #{top_rated.rank} ({top_rated.offer.title}) "
            f"rated {top_rated.offer.rating:.1f}/5 ({top_rated.offer.review_count} reviews)."
        )
    details = [_format_offer_line(item, language) for item in offers]
    return "\n".join([*highlights, *details])


def render_clarification_message(
    *,
    language: Literal["ar", "en"],
    question: str | None = None,
    missing_saved_offers_for_compare: bool = False,
) -> str:
    """Render clarification prompt or empty-saved-offers guidance."""
    if missing_saved_offers_for_compare:
        if language == "ar":
            return (
                "لا توجد عروض محفوظة للمقارنة حالياً. "
                "ابحث عن منتج أولاً وسأعرض لك أفضل العروض الموثقة ثم يمكننا المقارنة بينها."
            )
        return (
            "There are no saved offers to compare yet. "
            "Search for a product first, and I will compare the verified results for you."
        )

    if question is not None and question.strip():
        return question.strip()

    if language == "ar":
        return (
            "ما المنتج أو الفئة التي تبحث عنها تحديداً (مثل: سماعات أنكر، آيفون 15، قلاية هوائية)؟"
        )
    return (
        "Which specific product or category are you looking for "
        "(for example: Anker earbuds, iPhone 15, or an air fryer)?"
    )


def render_off_topic_message(*, language: Literal["ar", "en"]) -> str:
    """Render polite redirect keeping conversation within shopping assistance scope."""
    if language == "ar":
        return (
            "أنا مساعد تسوق متخصص في البحث عن المنتجات ومقارنة الأسعار الموثقة "
            "عبر نون وأمازون في مصر والسعودية والإمارات. "
            "اكتب اسم المنتج الذي تبحث عنه وسأساعدك فوراً."
        )
    return (
        "I am a shopping assistant focused on finding and comparing verified product offers "
        "across Noon and Amazon in Egypt, Saudi Arabia, and UAE. "
        "Tell me which product you are looking for and I will help right away."
    )


def render_refused_message(
    *,
    language: Literal["ar", "en"],
    reason_code: str | None = None,
) -> str:
    """Render safe guardrail refusal without echoing any raw PII, secrets, or injection text."""
    if language == "ar":
        if reason_code == "sensitive_pii_payment":
            return (
                "عذراً، لا يمكنني استقبال أو معالجة أرقام البطاقات البنكية أو رموز الأمان "
                "أو كلمات المرور أو الهويات الوطنية. يمكنك إرسال اسم المنتج والميزانية فقط."
            )
        if reason_code == "max_length_exceeded":
            return "عذراً، الرسالة أطول من الحد المسموح به. يرجى اختصار طلب التسوق وإعادة الإرسال."
        if reason_code == "empty_message":
            return "يرجى إدخال طلب تسوق واضح يحتوي على اسم المنتج أو الفئة المطلوبة."
        return (
            "عذراً، تعذر قبول هذه الرسالة لأسباب تتعلق بالأمان وضوابط الاستخدام. "
            "يرجى كتابة طلب البحث عن المنتجات فقط."
        )

    if reason_code == "sensitive_pii_payment":
        return (
            "I cannot accept or process payment card numbers, security codes, passwords, or "
            "national ID numbers. Please share only the product name and shopping preferences."
        )
    if reason_code == "max_length_exceeded":
        return (
            "Your message exceeds the maximum allowed length. Please shorten your shopping request."
        )
    if reason_code == "empty_message":
        return "Please enter a clear shopping query with the product or category you want."
    return (
        "Sorry, this request could not be processed due to input safety guardrails. "
        "Please send a standard product search request."
    )


def render_degraded_catalog_message(
    *,
    language: Literal["ar", "en"],
    retriable: bool = True,
) -> str:
    """Render honest catalog-provider outage notice without exposing internal details."""
    if language == "ar":
        if retriable:
            return (
                "خدمة البحث عن العروض غير متاحة مؤقتاً في الوقت الحالي. "
                "يرجى المحاولة مرة أخرى بعد لحظات."
            )
        return "تعذر الوصول إلى مزود العروض حالياً. يرجى المحاولة لاحقاً."

    if retriable:
        return (
            "The marketplace catalog service is temporarily unavailable. "
            "Please try again in a moment."
        )
    return "The marketplace catalog provider is currently unavailable. Please try again later."
