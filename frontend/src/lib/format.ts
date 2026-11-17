import {
  MAX_BUDGET_LIMIT,
  type BudgetValidationError,
  type CurrencyCode,
  type DecimalString,
  type UiLanguage,
} from "@/lib/contracts";

const CURRENCY_LABELS: Record<CurrencyCode, { ar: string; en: string }> = {
  EGP: { ar: "جنيه مصري", en: "EGP" },
  SAR: { ar: "ريال سعودي", en: "SAR" },
  AED: { ar: "درهم إماراتي", en: "AED" },
};

const MAX_BUDGET_CENTS = BigInt(MAX_BUDGET_LIMIT) * 100n;
const POSITIVE_DECIMAL_RE = /^\+?(?:(\d+)(?:\.(\d+))?|\.(\d+))$/;
const NEGATIVE_DECIMAL_RE = /^-(?:(\d+)(?:\.(\d+))?|\.(\d+))$/;

export interface BudgetValidationResult {
  valid: boolean;
  normalized: DecimalString | null;
  error: BudgetValidationError | null;
}

export function getCurrencyLabel(currency: CurrencyCode, language: UiLanguage): string {
  return CURRENCY_LABELS[currency][language];
}

/**
 * Validate optional user budget input against backend `MAX_BUDGET_DECIMAL` (`> 0 && <= 10000000.00`)
 * using exact decimal string math with zero IEEE-754 float precision loss.
 */
export function validateBudgetInput(raw: string): BudgetValidationResult {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { valid: true, normalized: null, error: null };
  }

  if (NEGATIVE_DECIMAL_RE.test(trimmed)) {
    return { valid: false, normalized: null, error: "non_positive" };
  }

  const match = POSITIVE_DECIMAL_RE.exec(trimmed);
  if (!match) {
    return { valid: false, normalized: null, error: "invalid_number" };
  }

  const rawInt = match[1] ?? "0";
  const rawFrac = match[2] ?? match[3] ?? "";
  const cleanInt = rawInt.replace(/^0+(?=\d)/, "") || "0";

  const intBig = BigInt(cleanInt);
  const hasNonZeroFrac = /[1-9]/.test(rawFrac);

  if (intBig === 0n && !hasNonZeroFrac) {
    return { valid: false, normalized: null, error: "non_positive" };
  }

  if (intBig > BigInt(MAX_BUDGET_LIMIT) || (intBig === BigInt(MAX_BUDGET_LIMIT) && hasNonZeroFrac)) {
    return { valid: false, normalized: null, error: "exceeds_max" };
  }

  const paddedFrac = `${rawFrac}000`.slice(0, 3);
  const twoDigits = BigInt(paddedFrac.slice(0, 2));
  const roundUp = Number(paddedFrac[2] ?? "0") >= 5 ? 1n : 0n;
  const cents = intBig * 100n + twoDigits + roundUp;

  if (cents <= 0n) {
    return { valid: false, normalized: null, error: "non_positive" };
  }
  if (cents > MAX_BUDGET_CENTS) {
    return { valid: false, normalized: null, error: "exceeds_max" };
  }

  const whole = cents / 100n;
  const fraction = (cents % 100n).toString().padStart(2, "0");
  return {
    valid: true,
    normalized: `${whole.toString()}.${fraction}`,
    error: null,
  };
}

/**
 * Format a backend `DecimalString` price with comma grouping while preserving exact
 * fractional digits verbatim (never converting through JS `Number`).
 */
export function formatExactPrice(
  price: DecimalString,
  currency: CurrencyCode,
  language: UiLanguage,
): string {
  const trimmed = price.trim();
  const currencyLabel = getCurrencyLabel(currency, language);
  const match = /^(-)?(\d+)(?:\.(\d+))?$/.exec(trimmed);
  if (!match) {
    return `${trimmed} ${currencyLabel}`;
  }

  const sign = match[1] ?? "";
  const intDigits = (match[2] ?? "0").replace(/^0+(?=\d)/, "") || "0";
  const fracDigits = match[3];
  const groupedInt = intDigits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const formattedNumber =
    fracDigits !== undefined ? `${sign}${groupedInt}.${fracDigits}` : `${sign}${groupedInt}`;

  return `${formattedNumber} ${currencyLabel}`;
}

export function formatRatingValue(
  rating: number | null,
  reviewCount: number,
  language: UiLanguage,
): string {
  if (rating === null || !Number.isFinite(rating) || reviewCount <= 0) {
    return language === "ar" ? "غير مُقيّم" : "Unrated";
  }
  const formattedCount = reviewCount.toLocaleString("en-US");
  if (language === "ar") {
    return `${rating.toFixed(1)} / 5 (${formattedCount} مراجعة)`;
  }
  return `${rating.toFixed(1)} / 5 (${formattedCount} reviews)`;
}

export function formatBayesianScore(score: number): string {
  const safe = Number.isFinite(score) ? Math.min(5, Math.max(0, score)) : 0;
  return `${safe.toFixed(2)} / 5.0`;
}

export function formatValueScore(score: number): string {
  const safe = Number.isFinite(score) ? Math.min(100, Math.max(0, score)) : 0;
  return `${safe.toFixed(1)} / 100`;
}

export function formatLatencyMs(latencyMs: number, language: UiLanguage): string {
  if (!Number.isFinite(latencyMs) || latencyMs < 0) {
    return language === "ar" ? "0 مللي ثانية" : "0 ms";
  }
  const rounded = latencyMs > 0 && latencyMs < 10 ? latencyMs.toFixed(1) : Math.round(latencyMs).toString();
  return language === "ar" ? `${rounded} مللي ثانية` : `${rounded} ms`;
}

/**
 * Enforce strict `https://`-only URLs for outbound links and product images (`INV-05`, `INV-09`).
 * Rejects `http:`, `javascript:`, `data:`, `vbscript:`, embedded credentials, backslashes,
 * whitespace, and ASCII/C1 control characters.
 */
export function sanitizeHttpsUrl(rawUrl: string | null | undefined): string | null {
  if (typeof rawUrl !== "string" || rawUrl.length === 0) {
    return null;
  }
  if (/[\s\\\u0000-\u001F\u007F-\u009F]/.test(rawUrl)) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }

  if (parsed.protocol !== "https:") {
    return null;
  }
  if (!parsed.hostname) {
    return null;
  }
  if (parsed.username !== "" || parsed.password !== "") {
    return null;
  }

  const authority = rawUrl.slice("https://".length).split(/[/?#]/, 1)[0] ?? "";
  if (authority.includes("@")) {
    return null;
  }

  return parsed.href;
}
