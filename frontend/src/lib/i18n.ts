import type {
  BudgetValidationError,
  CountryCode,
  HealthStatus,
  MatchReasonCode,
  StoreFilter,
  TurnAction,
  TurnStatus,
  UiLanguage,
} from "@/lib/contracts";

export interface StarterPrompt {
  id: string;
  labelAr: string;
  labelEn: string;
  queryAr: string;
  queryEn: string;
}

export const STARTER_PROMPTS: Record<CountryCode, StarterPrompt[]> = {
  EG: [
    {
      id: "eg-anker-earbuds",
      labelAr: "سماعة بلوتوث أنكر",
      labelEn: "Anker earbuds",
      queryAr: "أفضل سماعة بلوتوث أنكر في مصر تحت 3500 جنيه",
      queryEn: "Best Anker wireless earbuds in Egypt under 3500 EGP",
    },
    {
      id: "eg-air-fryer",
      labelAr: "قلاية هوائية",
      labelEn: "Air fryer",
      queryAr: "أفضل قلاية هوائية عائلية في مصر من نون وأمازون",
      queryEn: "Compare family air fryers in Egypt across Noon and Amazon",
    },
    {
      id: "eg-iphone-15",
      labelAr: "آيفون 15",
      labelEn: "iPhone 15",
      queryAr: "أفضل سعر لهاتف أبل آيفون 15 في مصر",
      queryEn: "Best verified Apple iPhone 15 deal in Egypt",
    },
  ],
  SA: [
    {
      id: "sa-anker-earbuds",
      labelAr: "سماعة بلوتوث أنكر",
      labelEn: "Anker earbuds",
      queryAr: "أفضل سماعة بلوتوث أنكر في السعودية تحت 300 ريال",
      queryEn: "Best Anker wireless earbuds in Saudi Arabia under 300 SAR",
    },
    {
      id: "sa-air-fryer",
      labelAr: "قلاية هوائية",
      labelEn: "Air fryer",
      queryAr: "قلاية هوائية فيليبس أو نينجا في السعودية",
      queryEn: "Compare Philips and Ninja air fryers in Saudi Arabia",
    },
    {
      id: "sa-iphone-15",
      labelAr: "آيفون 15",
      labelEn: "iPhone 15",
      queryAr: "مقارنة أسعار آيفون 15 في نون وأمازون السعودية",
      queryEn: "Compare Apple iPhone 15 offers on Noon and Amazon SA",
    },
  ],
  AE: [
    {
      id: "ae-anker-earbuds",
      labelAr: "سماعة بلوتوث أنكر",
      labelEn: "Anker earbuds",
      queryAr: "أفضل سماعة بلوتوث أنكر في الإمارات تحت 300 درهم",
      queryEn: "Best Anker wireless earbuds in UAE under 300 AED",
    },
    {
      id: "ae-air-fryer",
      labelAr: "قلاية هوائية",
      labelEn: "Air fryer",
      queryAr: "أفضل قلاية هوائية في الإمارات على نون وأمازون",
      queryEn: "Top rated air fryers in UAE across Noon and Amazon",
    },
    {
      id: "ae-iphone-15",
      labelAr: "آيفون 15",
      labelEn: "iPhone 15",
      queryAr: "أفضل عرض آيفون 15 في الإمارات",
      queryEn: "Best verified Apple iPhone 15 offer in UAE",
    },
  ],
};

export const MATCH_REASON_LABELS: Record<MatchReasonCode, { ar: string; en: string }> = {
  best_overall_value: {
    ar: "أفضل قيمة إجمالية",
    en: "Best overall value",
  },
  lowest_price: {
    ar: "أقل سعر",
    en: "Lowest price",
  },
  top_bayesian_rating: {
    ar: "أعلى تقييم موثوق",
    en: "Top Bayesian rating",
  },
  high_review_confidence: {
    ar: "عدد مراجعات قوي",
    en: "High review confidence",
  },
  within_budget: {
    ar: "ضمن الميزانية",
    en: "Within budget",
  },
  unrated_fallback: {
    ar: "غير مُقيّم بعد",
    en: "Unrated fallback",
  },
  strong_value_runner_up: {
    ar: "بديل قوي للقيمة",
    en: "Strong runner-up",
  },
};

export const STORE_LABELS: Record<StoreFilter, { ar: string; en: string }> = {
  both: { ar: "الكل (نون وأمازون)", en: "Both (Noon & Amazon)" },
  noon: { ar: "نون", en: "Noon" },
  amazon: { ar: "أمازون", en: "Amazon" },
};

export function getMatchReasonLabel(code: string, language: UiLanguage): string {
  if (Object.prototype.hasOwnProperty.call(MATCH_REASON_LABELS, code)) {
    return MATCH_REASON_LABELS[code as MatchReasonCode][language];
  }
  return code;
}

export interface TranslationDictionary {
  brand: {
    title: string;
    subtitle: string;
    skipToMain: string;
  };
  shell: {
    controlsRegionLabel: string;
    marketLabel: string;
    storeLabel: string;
    budgetLabel: string;
    budgetPlaceholder: string;
    budgetClear: string;
    budgetHint: string;
    budgetErrors: Record<BudgetValidationError, string>;
    languageToggleLabel: string;
    switchToLanguageLabel: string;
    newChat: string;
    newChatAria: string;
    health: Record<HealthStatus, string> & { label: string; refreshAria: string };
    marketsFallbackNotice: string;
    workspaceSlotTitle: string;
    workspaceSlotDescription: string;
    workspaceSlotHint: string;
    stores: Record<StoreFilter, string>;
  };
  workspace: {
    modeToggleLabel: string;
    chatModeLabel: string;
    chatModeDesc: string;
    searchModeLabel: string;
    searchModeDesc: string;
    starterPromptsTitle: string;
    starterPromptsHint: string;
    chatThreadLabel: string;
    emptyChatTitle: string;
    emptyChatBody: string;
    userRoleLabel: string;
    assistantRoleLabel: string;
    loadingResponse: string;
    offersCountBadge: string;
    turnActions: Record<TurnAction, string>;
    turnStatuses: Record<TurnStatus, string>;
    composer: {
      chatLabel: string;
      chatPlaceholder: string;
      searchLabel: string;
      searchPlaceholder: string;
      sendButton: string;
      searchButton: string;
      sendingButton: string;
      minRatingLabel: string;
      minRatingAny: string;
      includeAccessoriesLabel: string;
      compareSavedButton: string;
      compareSavedHint: string;
      compareSavedDefaultQuery: string;
      validationQueryRequired: string;
      validationQueryTooLong: string;
      validationQueryUnsafeChars: string;
      validationBudgetBlocked: string;
    };
    mobileQuickJump: {
      label: string;
      comparisonHeading: string;
    };
    comparison: {
      panelTitle: string;
      panelEmptyTitle: string;
      panelEmptyBody: string;
      offersFoundLabel: string;
      rankPrefix: string;
      valueScoreLabel: string;
      bayesianRatingLabel: string;
      rawRatingLabel: string;
      unratedBadge: string;
      openStoreCta: string;
      unavailableLinkCta: string;
      imageFallbackAlt: string;
      outOfStockBadge: string;
    };
    telemetry: {
      title: string;
      sourceSeed: string;
      sourceLive: string;
      sourceSaved: string;
      cacheHit: string;
      cacheMiss: string;
      llmCalls: string;
      latency: string;
      requestId: string;
      totalCandidates: string;
      filteredAccessories: string;
      filteredOutliers: string;
    };
    banners: {
      clarifyTitle: string;
      clarifyHint: string;
      offTopicTitle: string;
      offTopicHint: string;
      refusedTitle: string;
      refusedHint: string;
      redactedUserMessage: string;
      degradedTitle: string;
      degradedHint: string;
      partialResultsTitle: string;
      partialResultsHint: string;
      noResultsTitle: string;
      noResultsHint: string;
      rateLimitTitle: string;
      rateLimitWithSeconds: string;
      rateLimitGeneric: string;
      networkErrorTitle: string;
      networkErrorBody: string;
      retryButton: string;
    };
    matchReasons: Record<MatchReasonCode, string>;
  };
}

const AR_DICTIONARY: TranslationDictionary = {
  brand: {
    title: "مساعد التسوق الذكي",
    subtitle: "مقارنة موثقة لأفضل 3 عروض من نون وأمازون في مصر والسعودية والإمارات",
    skipToMain: "انتقل إلى مساحة التسوق",
  },
  shell: {
    controlsRegionLabel: "إعدادات السوق والمتجر والميزانية",
    marketLabel: "السوق والعملة",
    storeLabel: "المتجر",
    budgetLabel: "أقصى ميزانية",
    budgetPlaceholder: "مثال: 3500",
    budgetClear: "مسح",
    budgetHint: "اختياري — بعملة السوق المختار (حتى 10,000,000)",
    budgetErrors: {
      invalid_number: "أدخل رقماً صحيحاً للميزانية بدون حروف أو رموز علمية.",
      non_positive: "يجب أن تكون الميزانية أكبر من صفر.",
      exceeds_max: "الحد الأقصى للميزانية المسموح به هو 10,000,000.",
    },
    languageToggleLabel: "تبديل اللغة",
    switchToLanguageLabel: "English (LTR)",
    newChat: "محادثة جديدة",
    newChatAria: "بدء محادثة جديدة لهذا السوق فقط",
    health: {
      label: "حالة الخدمة",
      checking: "جارٍ الفحص...",
      ok: "متصل",
      degraded: "تشغيل مقلّص",
      offline: "غير متصل",
      refreshAria: "تحديث حالة الخدمة",
    },
    marketsFallbackNotice: "تعذر تحديث قائمة الأسواق من الخادم؛ يتم عرض الأسواق الافتراضية محلياً.",
    workspaceSlotTitle: "مساحة المحادثة ومقارنة أفضل 3 عروض",
    workspaceSlotDescription:
      "تم تجهيز غلاف التطبيق العربي (RTL)، ومحددات السوق والمتجر والميزانية، ووكيل الاتصال الآمن بالخادم الخلفي.",
    workspaceSlotHint: "سيتم تفعيل وحدة المحادثة والبحث المباشر وبطاقات المقارنة في الميزة التالية.",
    stores: {
      both: "الكل (نون وأمازون)",
      noon: "نون",
      amazon: "أمازون",
    },
  },
  workspace: {
    modeToggleLabel: "وضع البحث والتسوق",
    chatModeLabel: "المساعد التفاعلي",
    chatModeDesc: "محادثة ذكية تفهم طلبك بالعربية أو الإنجليزية",
    searchModeLabel: "بحث مباشر (بدون LLM)",
    searchModeDesc: "ترتيب فوري حتمي بصفر استدعاءات للذكاء الاصطناعي",
    starterPromptsTitle: "اقتراحات سريعة لهذا السوق",
    starterPromptsHint: "اضغط على أي مثال للبدء فوراً:",
    chatThreadLabel: "سجل المحادثة",
    emptyChatTitle: "ابدأ بسؤال عن أي منتج",
    emptyChatBody:
      "اكتب اسم المنتج ومواصفاته أو اختر أحد الاقتراحات السريعة لعرض أفضل 3 عروض موثقة.",
    userRoleLabel: "أنت",
    assistantRoleLabel: "المساعد",
    loadingResponse: "جارٍ البحث ومقارنة العروض الموثقة...",
    offersCountBadge: "عروض موثقة",
    turnActions: {
      search: "بحث",
      compare: "مقارنة",
      clarify: "توضيح",
      off_topic: "خارج النطاق",
      refuse: "مرفوض",
    },
    turnStatuses: {
      ok: "مكتمل",
      clarify: "يحتاج توضيحاً",
      off_topic: "خارج نطاق التسوق",
      refused: "مرفوض أمنياً",
      degraded: "خدمة متأثرة",
    },
    composer: {
      chatLabel: "رسالة البحث أو المقارنة",
      chatPlaceholder: "مثال: أريد سماعة بلوتوث أنكر ممتازة تحت الميزانية...",
      searchLabel: "كلمة البحث المباشر",
      searchPlaceholder: "مثال: Anker Soundcore أو قلاية هوائية...",
      sendButton: "إرسال",
      searchButton: "بحث مباشر",
      sendingButton: "جارٍ التنفيذ...",
      minRatingLabel: "الحد الأدنى للتقييم",
      minRatingAny: "أي تقييم",
      includeAccessoriesLabel: "تضمين الإكسسوارات والملحقات",
      compareSavedButton: "قارن أفضل العروض",
      compareSavedHint: "مقارنة جانبية سريعة للعروض المحفوظة حالياً",
      compareSavedDefaultQuery: "مقارنة العروض المحفوظة",
      validationQueryRequired: "يرجى إدخال اسم المنتج أو عبارة البحث قبل الإرسال.",
      validationQueryTooLong: "عبارة البحث يجب ألا تتجاوز 500 حرف.",
      validationQueryUnsafeChars: "عبارة البحث تحتوي على محارف تحكم غير مسموح بها.",
      validationBudgetBlocked: "صحح قيمة الميزانية أعلاه قبل إرسال الطلب.",
    },
    mobileQuickJump: {
      label: "الانتقال إلى جدول المقارنة",
      comparisonHeading: "أفضل العروض",
    },
    comparison: {
      panelTitle: "أفضل 3 عروض موثقة",
      panelEmptyTitle: "لا توجد عروض معروضة بعد",
      panelEmptyBody:
        "عند إرسال طلبك أو إجراء بحث مباشر ستظهر هنا أفضل العروض الموثقة من نون وأمازون مرتبة حسب القيمة.",
      offersFoundLabel: "عروض معروضة",
      rankPrefix: "#",
      valueScoreLabel: "نقاط القيمة",
      bayesianRatingLabel: "التقييم الموزون (Bayesian)",
      rawRatingLabel: "تقييم المتجر",
      unratedBadge: "غير مُقيّم",
      openStoreCta: "عرض العرض في المتجر",
      unavailableLinkCta: "رابط غير متاح بأمان",
      imageFallbackAlt: "صورة غير متوفرة للمنتج",
      outOfStockBadge: "غير متوفر حالياً",
    },
    telemetry: {
      title: "بيانات المصدر والتكلفة",
      sourceSeed: "بيانات تجريبية",
      sourceLive: "بحث مباشر",
      sourceSaved: "مقارنة عروض محفوظة",
      cacheHit: "من الذاكرة المؤقتة",
      cacheMiss: "استعلام جديد",
      llmCalls: "استدعاءات LLM",
      latency: "الاستجابة",
      requestId: "معرّف الطلب",
      totalCandidates: "إجمالي المرشحين",
      filteredAccessories: "ملحقات مستبعدة",
      filteredOutliers: "أسعار شاذة مستبعدة",
    },
    banners: {
      clarifyTitle: "نحتاج مزيداً من التفاصيل",
      clarifyHint: "أضف اسم المنتج أو الفئة لنبحث لك عن أفضل العروض الموثقة.",
      offTopicTitle: "الطلب خارج نطاق التسوق",
      offTopicHint: "يمكنني مساعدتك فقط في البحث ومقارنة المنتجات على نون وأمازون.",
      refusedTitle: "تم حجب الإدخال لحماية الأمان والخصوصية",
      refusedHint: "لا ترسل أرقام بطاقات بنكية أو كلمات مرور أو أرقام هوية؛ اكتب اسم المنتج فقط.",
      redactedUserMessage: "[رسالة محجوبة لحماية الخصوصية]",
      degradedTitle: "تعذر جلب عروض جديدة مؤقتاً",
      degradedHint: "خدمة مزود العروض متأثرة حالياً؛ يمكنك إعادة المحاولة بعد قليل.",
      partialResultsTitle: "نتائج جزئية موثقة (أقل من 3 عروض)",
      partialResultsHint: "نلتزم بعرض العروض الحقيقية المؤهلة فقط دون اختلاق نتائج إضافية.",
      noResultsTitle: "لا توجد عروض مطابقة حالياً",
      noResultsHint: "جرّب توسيع المتجر إلى (الكل) أو رفع الحد الأقصى للميزانية أو تعديل البحث.",
      rateLimitTitle: "تم تجاوز الحد المؤقت للطلبات (429)",
      rateLimitWithSeconds: "يرجى الانتظار {seconds} ثانية ثم إعادة المحاولة.",
      rateLimitGeneric: "يرجى الانتظار لحظات ثم إعادة المحاولة.",
      networkErrorTitle: "تعذر الاتصال بالخادم (503)",
      networkErrorBody: "الخادم الخلفي غير متاح حالياً أو انتهت مهلة الاتصال.",
      retryButton: "إعادة المحاولة",
    },
    matchReasons: {
      best_overall_value: MATCH_REASON_LABELS.best_overall_value.ar,
      lowest_price: MATCH_REASON_LABELS.lowest_price.ar,
      top_bayesian_rating: MATCH_REASON_LABELS.top_bayesian_rating.ar,
      high_review_confidence: MATCH_REASON_LABELS.high_review_confidence.ar,
      within_budget: MATCH_REASON_LABELS.within_budget.ar,
      unrated_fallback: MATCH_REASON_LABELS.unrated_fallback.ar,
      strong_value_runner_up: MATCH_REASON_LABELS.strong_value_runner_up.ar,
    },
  },
};

const EN_DICTIONARY: TranslationDictionary = {
  brand: {
    title: "Smart Shopping Advisor",
    subtitle: "Verified Top-3 Noon & Amazon comparisons across Egypt, Saudi Arabia, and UAE",
    skipToMain: "Skip to shopping workspace",
  },
  shell: {
    controlsRegionLabel: "Market, store, and budget controls",
    marketLabel: "Market & Currency",
    storeLabel: "Store",
    budgetLabel: "Max Budget",
    budgetPlaceholder: "e.g. 3500",
    budgetClear: "Clear",
    budgetHint: "Optional — in active market currency (up to 10,000,000)",
    budgetErrors: {
      invalid_number: "Enter a valid decimal number without letters or scientific notation.",
      non_positive: "Budget must be greater than 0.",
      exceeds_max: "Maximum allowed budget is 10,000,000.",
    },
    languageToggleLabel: "Switch language",
    switchToLanguageLabel: "العربية (RTL)",
    newChat: "New Chat",
    newChatAria: "Start a new chat for the active market only",
    health: {
      label: "Service Status",
      checking: "Checking...",
      ok: "Connected",
      degraded: "Degraded",
      offline: "Offline",
      refreshAria: "Refresh service status",
    },
    marketsFallbackNotice: "Could not refresh markets from backend; using built-in market defaults.",
    workspaceSlotTitle: "Chat & Top-3 Product Comparison Workspace",
    workspaceSlotDescription:
      "Arabic-first RTL shell, market/store/budget selectors, and runtime same-origin backend proxy are ready.",
    workspaceSlotHint: "Interactive chat, zero-LLM search, and Top-3 comparison cards attach in Feature 3.2.",
    stores: {
      both: "Both (Noon & Amazon)",
      noon: "Noon",
      amazon: "Amazon",
    },
  },
  workspace: {
    modeToggleLabel: "Shopping Mode",
    chatModeLabel: "Conversational Assistant",
    chatModeDesc: "Bilingual AI assistant for guided search & follow-ups",
    searchModeLabel: "Zero-LLM Direct Search",
    searchModeDesc: "Deterministic ranking with 0 LLM calls",
    starterPromptsTitle: "Quick Prompts for This Market",
    starterPromptsHint: "Click an example query to start immediately:",
    chatThreadLabel: "Conversation History",
    emptyChatTitle: "Ask about any product",
    emptyChatBody:
      "Enter a product name and budget or pick a quick starter prompt to inspect the Top-3 verified offers.",
    userRoleLabel: "You",
    assistantRoleLabel: "Advisor",
    loadingResponse: "Searching and ranking verified marketplace offers...",
    offersCountBadge: "verified offers",
    turnActions: {
      search: "Search",
      compare: "Compare",
      clarify: "Clarify",
      off_topic: "Off-topic",
      refuse: "Refused",
    },
    turnStatuses: {
      ok: "OK",
      clarify: "Needs clarification",
      off_topic: "Off-topic",
      refused: "Refused",
      degraded: "Degraded",
    },
    composer: {
      chatLabel: "Shopping message",
      chatPlaceholder: "e.g. Best Anker earbuds under budget...",
      searchLabel: "Direct search query",
      searchPlaceholder: "e.g. Anker Soundcore or air fryer...",
      sendButton: "Send",
      searchButton: "Direct Search",
      sendingButton: "Working...",
      minRatingLabel: "Minimum Rating",
      minRatingAny: "Any rating",
      includeAccessoriesLabel: "Include accessories & parts",
      compareSavedButton: "Compare Saved Offers",
      compareSavedHint: "Side-by-side comparison of currently saved offers",
      compareSavedDefaultQuery: "Compare saved offers",
      validationQueryRequired: "Please enter a product name or search query first.",
      validationQueryTooLong: "Search query must be 500 characters or fewer.",
      validationQueryUnsafeChars: "Search query contains disallowed control characters.",
      validationBudgetBlocked: "Fix the budget cap error above before submitting.",
    },
    mobileQuickJump: {
      label: "Jump to Top-3 Comparison",
      comparisonHeading: "Top Offers",
    },
    comparison: {
      panelTitle: "Top-3 Verified Offers",
      panelEmptyTitle: "No offers displayed yet",
      panelEmptyBody:
        "Submit a chat query or direct search to compare verified Noon and Amazon offers ranked by value.",
      offersFoundLabel: "offers shown",
      rankPrefix: "#",
      valueScoreLabel: "Value Score",
      bayesianRatingLabel: "Bayesian Rating",
      rawRatingLabel: "Store Rating",
      unratedBadge: "Unrated",
      openStoreCta: "View Offer on Store",
      unavailableLinkCta: "Safe link unavailable",
      imageFallbackAlt: "Product image unavailable",
      outOfStockBadge: "Out of stock",
    },
    telemetry: {
      title: "Provenance & Cost Telemetry",
      sourceSeed: "Seed Demo",
      sourceLive: "Live Search",
      sourceSaved: "Saved Offer Comparison",
      cacheHit: "Cache Hit",
      cacheMiss: "Cache Miss",
      llmCalls: "LLM Calls",
      latency: "Latency",
      requestId: "Request ID",
      totalCandidates: "Total Candidates",
      filteredAccessories: "Accessories Filtered",
      filteredOutliers: "Outliers Filtered",
    },
    banners: {
      clarifyTitle: "More details needed",
      clarifyHint: "Specify a product name or category so we can fetch verified offers.",
      offTopicTitle: "Request is outside shopping scope",
      offTopicHint: "I can only assist with searching and comparing products on Noon and Amazon.",
      refusedTitle: "Input blocked by safety & privacy guardrails",
      refusedHint: "Do not submit payment card numbers, passwords, or IDs; share product queries only.",
      redactedUserMessage: "[Redacted sensitive input]",
      degradedTitle: "Catalog service temporarily degraded",
      degradedHint: "Upstream offer retrieval is unavailable right now; please retry shortly.",
      partialResultsTitle: "Partial verified results (fewer than 3 offers)",
      partialResultsHint: "Only genuine qualifying offers are displayed, with zero fabricated cards.",
      noResultsTitle: "No qualifying offers found",
      noResultsHint: "Try broadening the store filter to Both, raising Max Budget, or adjusting the query.",
      rateLimitTitle: "Rate limit exceeded (429)",
      rateLimitWithSeconds: "Please wait {seconds} seconds before retrying.",
      rateLimitGeneric: "Please wait a moment before retrying.",
      networkErrorTitle: "Backend service unreachable (503)",
      networkErrorBody: "The backend API is currently offline or timed out.",
      retryButton: "Retry",
    },
    matchReasons: {
      best_overall_value: MATCH_REASON_LABELS.best_overall_value.en,
      lowest_price: MATCH_REASON_LABELS.lowest_price.en,
      top_bayesian_rating: MATCH_REASON_LABELS.top_bayesian_rating.en,
      high_review_confidence: MATCH_REASON_LABELS.high_review_confidence.en,
      within_budget: MATCH_REASON_LABELS.within_budget.en,
      unrated_fallback: MATCH_REASON_LABELS.unrated_fallback.en,
      strong_value_runner_up: MATCH_REASON_LABELS.strong_value_runner_up.en,
    },
  },
};

export function getDictionary(language: UiLanguage): TranslationDictionary {
  return language === "ar" ? AR_DICTIONARY : EN_DICTIONARY;
}
