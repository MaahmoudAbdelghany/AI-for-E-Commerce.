import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatThread } from "@/components/workspace/ChatThread";
import { OfferCard } from "@/components/workspace/OfferCard";
import { ProductComparisonGrid } from "@/components/workspace/ProductComparisonGrid";
import { StatusBanner } from "@/components/workspace/StatusBanner";
import { TelemetryStrip } from "@/components/workspace/TelemetryStrip";
import type { MatchReasonCode, RankedOffer, RankingResult } from "@/lib/contracts";
import { getDictionary, MATCH_REASON_LABELS } from "@/lib/i18n";

function buildOffer(overrides: Partial<RankedOffer> = {}): RankedOffer {
  const base: RankedOffer = {
    rank: 1,
    offer: {
      offer_id: "eg-noon-anker-l4nc",
      title: "Anker Soundcore Liberty 4 NC",
      price: "3299.00",
      currency: "EGP",
      store: "noon",
      country: "EG",
      url: "https://www.noon.com/egypt-ar/anker-l4nc/p/",
      rating: 4.7,
      review_count: 620,
      image_url: "https://f.nooncdn.com/p/anker.jpg",
      in_stock: true,
    },
    value_score: 88.5,
    price_norm: 0.72,
    bayesian_rating: 4.65,
    match_reasons: ["best_overall_value", "within_budget"],
  };

  return {
    ...base,
    ...overrides,
    offer: {
      ...base.offer,
      ...(overrides.offer ?? {}),
    },
  };
}

const ALL_REASON_CODES: MatchReasonCode[] = [
  "best_overall_value",
  "lowest_price",
  "top_bayesian_rating",
  "high_review_confidence",
  "within_budget",
  "unrated_fallback",
  "strong_value_runner_up",
];

describe("OfferCard, ProductComparisonGrid, TelemetryStrip, and StatusBanner (unit)", () => {
  it("OfferCard renders grounded price, Bayesian rating, value bar, store badge, and all 7 bilingual match reasons", () => {
    const offerWithAllReasons = buildOffer({
      rank: 2,
      offer: {
        offer_id: "eg-amazon-anker-r50i",
        title: "سماعة أنكر Soundcore R50i",
        price: "3299.00",
        currency: "EGP",
        store: "amazon",
        country: "EG",
        url: "https://www.amazon.eg/dp/B0C3ANKEG1",
        rating: 4.7,
        review_count: 620,
        image_url: "https://m.media-amazon.com/images/I/anker.jpg",
        in_stock: true,
      },
      value_score: 91.2,
      bayesian_rating: 4.65,
      match_reasons: ALL_REASON_CODES,
    });

    const arDict = getDictionary("ar");
    const { rerender } = render(
      <OfferCard rankedOffer={offerWithAllReasons} language="ar" t={arDict} />,
    );

    const mixedHeading = screen.getByRole("heading", {
      level: 3,
      name: "سماعة أنكر Soundcore R50i",
    });
    expect(mixedHeading).toBeInTheDocument();
    expect(mixedHeading).toHaveAttribute("dir", "auto");

    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.getByText("أمازون")).toBeInTheDocument();
    expect(screen.getByText("3,299.00 جنيه مصري")).toBeInTheDocument();
    expect(screen.getByText("4.7 / 5 (620 مراجعة)")).toBeInTheDocument();
    expect(screen.getByText("4.65 / 5.0")).toBeInTheDocument();
    expect(screen.getByText("91.2 / 100")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "91.2");

    for (const code of ALL_REASON_CODES) {
      expect(screen.getByText(MATCH_REASON_LABELS[code].ar)).toBeInTheDocument();
    }

    const enDict = getDictionary("en");
    const noonOffer = buildOffer({
      rank: 1,
      match_reasons: ALL_REASON_CODES,
    });
    rerender(<OfferCard rankedOffer={noonOffer} language="en" t={enDict} />);

    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("Noon")).toBeInTheDocument();
    expect(screen.getByText("3,299.00 EGP")).toBeInTheDocument();
    expect(screen.getByText("4.7 / 5 (620 reviews)")).toBeInTheDocument();
    for (const code of ALL_REASON_CODES) {
      expect(screen.getByText(MATCH_REASON_LABELS[code].en)).toBeInTheDocument();
    }
  });

  it("OfferCard renders explicit Unrated badge when rating is null or review_count is 0", () => {
    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");

    const nullRatingOffer = buildOffer({
      offer: {
        offer_id: "unrated-1",
        title: "Unrated Product A",
        price: "500.00",
        currency: "EGP",
        store: "noon",
        country: "EG",
        url: "https://www.noon.com/egypt-ar/p/1",
        rating: null,
        review_count: 0,
        image_url: null,
        in_stock: true,
      },
      match_reasons: ["unrated_fallback"],
    });

    const zeroReviewsOffer = buildOffer({
      offer: {
        offer_id: "unrated-2",
        title: "Unrated Product B",
        price: "600.00",
        currency: "EGP",
        store: "amazon",
        country: "EG",
        url: "https://www.amazon.eg/dp/B0000001",
        rating: 4.5,
        review_count: 0,
        image_url: null,
        in_stock: true,
      },
    });

    const { rerender } = render(
      <OfferCard rankedOffer={nullRatingOffer} language="ar" t={arDict} />,
    );
    expect(screen.getByText("غير مُقيّم")).toBeInTheDocument();
    expect(screen.queryByText(/مراجعة/)).not.toBeInTheDocument();

    rerender(<OfferCard rankedOffer={zeroReviewsOffer} language="en" t={enDict} />);
    expect(screen.getByText("Unrated")).toBeInTheDocument();
    expect(screen.queryByText(/4\.5 \/ 5/)).not.toBeInTheDocument();
  });

  it("OfferCard enforces strict https image fallback and noopener noreferrer outbound CTA guard", () => {
    const enDict = getDictionary("en");

    const validOffer = buildOffer({
      offer: {
        offer_id: "safe-offer",
        title: "Safe HTTPS Offer",
        price: "1500.00",
        currency: "EGP",
        store: "noon",
        country: "EG",
        url: "https://www.noon.com/egypt-en/safe-product/p/",
        rating: 4.5,
        review_count: 100,
        image_url: "https://f.nooncdn.com/p/safe.jpg",
        in_stock: true,
      },
    });

    const { container, rerender } = render(
      <OfferCard rankedOffer={validOffer} language="en" t={enDict} />,
    );

    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("src", "https://f.nooncdn.com/p/safe.jpg");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");

    const ctaLink = screen.getByRole("link", { name: enDict.workspace.comparison.openStoreCta });
    expect(ctaLink).toHaveAttribute("href", "https://www.noon.com/egypt-en/safe-product/p/");
    expect(ctaLink).toHaveAttribute("target", "_blank");
    expect(ctaLink).toHaveAttribute("rel", "noopener noreferrer");

    // Simulate broken CDN image -> falls back cleanly to inline SVG
    if (img) {
      fireEvent.error(img);
    }
    expect(container.querySelector("img")).toBeNull();
    expect(
      screen.getByRole("img", { name: enDict.workspace.comparison.imageFallbackAlt }),
    ).toBeInTheDocument();

    // Unsafe protocols on both image_url and url must never emit img src or anchor href
    const unsafeUrls: Array<{ imgUrl: string | null; offerUrl: string }> = [
      { imgUrl: null, offerUrl: "javascript:alert(1)" },
      { imgUrl: "http://cdn.example.com/a.jpg", offerUrl: "http://noon.com/item" },
      {
        imgUrl: "https://user:pass@cdn.example.com/a.jpg",
        offerUrl: "https://user:pass@amazon.eg/dp/1",
      },
    ];

    for (const pair of unsafeUrls) {
      const unsafeOffer = buildOffer({
        offer: {
          offer_id: `unsafe-${pair.offerUrl}`,
          title: "Unsafe URL Offer",
          price: "100.00",
          currency: "EGP",
          store: "amazon",
          country: "EG",
          url: pair.offerUrl,
          rating: 4.0,
          review_count: 10,
          image_url: pair.imgUrl,
          in_stock: true,
        },
      });
      rerender(<OfferCard rankedOffer={unsafeOffer} language="en" t={enDict} />);

      expect(container.querySelector("img")).toBeNull();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: enDict.workspace.comparison.unavailableLinkCta }),
      ).toBeDisabled();
    }
  });

  it("ProductComparisonGrid preserves exact server rank order without client sorting or fake padding", () => {
    const enDict = getDictionary("en");

    // Deliberately non-monotonic prices/value_score vs server rank 1, 2, 3
    const offers: RankedOffer[] = [
      buildOffer({
        rank: 1,
        value_score: 79.0,
        offer: {
          offer_id: "offer-a",
          title: "Server First Offer",
          price: "5000.00",
          currency: "EGP",
          store: "noon",
          country: "EG",
          url: "https://www.noon.com/p/a",
          rating: 4.8,
          review_count: 300,
          image_url: null,
          in_stock: true,
        },
      }),
      buildOffer({
        rank: 2,
        value_score: 95.0,
        offer: {
          offer_id: "offer-b",
          title: "Server Second Offer",
          price: "1200.00",
          currency: "EGP",
          store: "amazon",
          country: "EG",
          url: "https://www.amazon.eg/dp/B002",
          rating: 4.1,
          review_count: 20,
          image_url: null,
          in_stock: true,
        },
      }),
      buildOffer({
        rank: 3,
        value_score: 64.0,
        offer: {
          offer_id: "offer-c",
          title: "Server Third Offer",
          price: "2900.00",
          currency: "EGP",
          store: "noon",
          country: "EG",
          url: "https://www.noon.com/p/c",
          rating: 4.3,
          review_count: 50,
          image_url: null,
          in_stock: true,
        },
      }),
    ];

    const { rerender } = render(
      <ProductComparisonGrid rankedOffers={offers} language="en" t={enDict} />,
    );

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Server First Offer",
      "Server Second Offer",
      "Server Third Offer",
    ]);

    // Partial < 3 offers (1 card) -> zero synthetic placeholder padding
    rerender(
      <ProductComparisonGrid rankedOffers={[offers[0]!]} language="en" t={enDict} />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("1 offers shown")).toBeInTheDocument();

    // Partial < 3 offers (2 cards) -> strictly 2 cards
    rerender(
      <ProductComparisonGrid rankedOffers={[offers[0]!, offers[1]!]} language="en" t={enDict} />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByText("2 offers shown")).toBeInTheDocument();
  });

  it("TelemetryStrip displays source mode, cache hit/miss, LLM calls, latency, request_id, and filter counts", () => {
    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");
    const rankingResult: RankingResult = {
      ranked_offers: [],
      total_candidates: 12,
      filtered_accessories_count: 4,
      filtered_outliers_count: 2,
      degraded_fewer_than_k: false,
    };

    const { rerender } = render(
      <TelemetryStrip
        sourceMode="seed"
        cacheHit={false}
        llmCalls={1}
        latencyMs={42.4}
        requestId="req-seed-1"
        rankingResult={rankingResult}
        language="ar"
        t={arDict}
      />,
    );

    expect(screen.getByText("بيانات تجريبية")).toBeInTheDocument();
    expect(screen.getByText("استعلام جديد")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("42 مللي ثانية")).toBeInTheDocument();
    expect(screen.getByText("req-seed-1")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();

    rerender(
      <TelemetryStrip
        sourceMode="live"
        cacheHit={true}
        llmCalls={0}
        latencyMs={8.6}
        requestId="req-live-2"
        rankingResult={rankingResult}
        language="en"
        t={enDict}
      />,
    );

    expect(screen.getByText("Live Search")).toBeInTheDocument();
    expect(screen.getByText("Cache Hit")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("8.6 ms")).toBeInTheDocument();
    expect(screen.getByText("req-live-2")).toBeInTheDocument();

    rerender(
      <TelemetryStrip
        sourceMode={null}
        cacheHit={false}
        llmCalls={1}
        latencyMs={15}
        requestId="req-compare-3"
        rankingResult={null}
        language="en"
        t={enDict}
      />,
    );

    expect(screen.getByText("Saved Offer Comparison")).toBeInTheDocument();
    expect(screen.getByText("Cache Miss")).toBeInTheDocument();
    expect(screen.queryByText(enDict.workspace.telemetry.totalCandidates)).not.toBeInTheDocument();
  });

  it("StatusBanner renders accessible bilingual banners for clarify, off_topic, refused, degraded, partial, empty, 429, and 503 with retry", async () => {
    const user = userEvent.setup();
    const arDict = getDictionary("ar");
    const enDict = getDictionary("en");
    const onRetry = vi.fn();

    const { rerender } = render(
      <StatusBanner kind="clarify" t={arDict} detailMessage="حدد الفئة المطلوبة" />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(arDict.workspace.banners.clarifyTitle);
    expect(screen.getByRole("status")).toHaveTextContent("حدد الفئة المطلوبة");

    rerender(<StatusBanner kind="off_topic" t={enDict} />);
    expect(screen.getByRole("status")).toHaveTextContent(enDict.workspace.banners.offTopicTitle);

    // Must never echo detailMessage when kind === "refused" (INV-09)
    rerender(
      <StatusBanner kind="refused" t={arDict} detailMessage="4111111111111111" />,
    );
    const refusedAlert = screen.getByRole("alert");
    expect(refusedAlert).toHaveTextContent(arDict.workspace.banners.refusedTitle);
    expect(refusedAlert).not.toHaveTextContent("4111111111111111");

    rerender(<StatusBanner kind="degraded" t={enDict} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(enDict.workspace.banners.degradedTitle);

    rerender(<StatusBanner kind="partial" t={arDict} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      arDict.workspace.banners.partialResultsTitle,
    );

    rerender(<StatusBanner kind="no_results" t={enDict} />);
    expect(screen.getByRole("status")).toHaveTextContent(enDict.workspace.banners.noResultsTitle);

    rerender(
      <StatusBanner kind="rate_limit" t={arDict} retryAfterSeconds={12} onRetry={onRetry} />,
    );
    const rateAlert = screen.getByRole("alert");
    expect(rateAlert).toHaveTextContent("429");
    expect(rateAlert).toHaveTextContent("12");

    rerender(<StatusBanner kind="network_error" t={enDict} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      enDict.workspace.banners.networkErrorTitle,
    );

    await user.click(screen.getByRole("button", { name: enDict.workspace.banners.retryButton }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("ChatThread isolates mixed Arabic/English user and assistant bubbles with dir=auto", () => {
    const arDict = getDictionary("ar");
    render(
      <ChatThread
        messages={[
          {
            id: "u-bidi",
            role: "user",
            content: "أفضل سماعة Anker Soundcore تحت 3500 EGP",
            createdAtIso: "2026-11-16T20:00:00Z",
          },
          {
            id: "a-bidi",
            role: "assistant",
            content: "أفضل عرض هو Anker Soundcore R50i بسعر 1,199.00 جنيه مصري.",
            createdAtIso: "2026-11-16T20:00:01Z",
            action: "search",
            status: "ok",
            offerCount: 1,
          },
        ]}
        isLoading={false}
        t={arDict}
      />,
    );

    const userBubbleText = screen.getByText("أفضل سماعة Anker Soundcore تحت 3500 EGP");
    const assistantBubbleText = screen.getByText(
      "أفضل عرض هو Anker Soundcore R50i بسعر 1,199.00 جنيه مصري.",
    );
    expect(userBubbleText).toHaveAttribute("dir", "auto");
    expect(assistantBubbleText).toHaveAttribute("dir", "auto");
  });
});
