import {
  MAX_BUDGET_LIMIT,
  type ChatRequest,
  type ChatResponse,
  type ErrorResponse,
  type HealthResponse,
  type MarketsResponse,
  type SearchRequest,
  type SearchResponse,
} from "@/lib/contracts";
import { validateBudgetInput } from "@/lib/format";

export interface ApiClientErrorParams {
  status: number;
  errorCode: string;
  message: string;
  retriable: boolean;
  requestId?: string;
  retryAfterSeconds?: number | null;
  details?: Array<Record<string, unknown>> | null;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly errorCode: string;
  readonly retriable: boolean;
  readonly requestId: string;
  readonly retryAfterSeconds: number | null;
  readonly details: Array<Record<string, unknown>> | null;

  constructor(params: ApiClientErrorParams) {
    super(params.message);
    this.name = "ApiClientError";
    this.status = params.status;
    this.errorCode = params.errorCode;
    this.retriable = params.retriable;
    this.requestId = params.requestId ?? "";
    this.retryAfterSeconds = params.retryAfterSeconds ?? null;
    this.details = params.details ?? null;
    Object.setPrototypeOf(this, ApiClientError.prototype);
  }
}

export function resolveApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!raw) {
    return "";
  }
  return raw.trim().replace(/\/+$/, "");
}

function parseRetryAfter(rawHeader: string | null): number | null {
  if (!rawHeader) {
    return null;
  }
  const trimmed = rawHeader.trim();
  if (/^\d+$/.test(trimmed)) {
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
  }
  return null;
}

function isErrorResponsePayload(value: unknown): value is Partial<ErrorResponse> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    typeof (value as Record<string, unknown>).error_code === "string"
  );
}

function sanitizeOutgoingMaxBudget(
  maxBudget: string | number | null | undefined,
): string | number | null | undefined {
  if (maxBudget === undefined || maxBudget === null) {
    return maxBudget;
  }
  if (typeof maxBudget === "number") {
    if (!Number.isFinite(maxBudget) || maxBudget <= 0 || maxBudget > MAX_BUDGET_LIMIT) {
      throw new ApiClientError({
        status: 422,
        errorCode: "invalid_budget",
        message: "max_budget must be a finite number > 0 and <= 10000000.00.",
        retriable: false,
      });
    }
    return maxBudget;
  }

  const validation = validateBudgetInput(maxBudget);
  if (!validation.valid || validation.normalized === null) {
    throw new ApiClientError({
      status: 422,
      errorCode: "invalid_budget",
      message: "max_budget must be a valid positive decimal <= 10000000.00.",
      retriable: false,
    });
  }
  return validation.normalized;
}

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiClientError({
      status: 0,
      errorCode: "network_error",
      message: "Unable to reach the service. Please check your connection and retry.",
      retriable: true,
    });
  }

  const headerRequestId = response.headers.get("x-request-id") ?? "";
  const retryAfterSeconds = parseRetryAfter(response.headers.get("retry-after"));
  const rawBody = await response.text();

  let parsed: unknown = null;
  if (rawBody.length > 0) {
    try {
      parsed = JSON.parse(rawBody);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    if (isErrorResponsePayload(parsed)) {
      throw new ApiClientError({
        status: response.status,
        errorCode: parsed.error_code ?? "http_error",
        message:
          typeof parsed.message === "string" && parsed.message.length > 0
            ? parsed.message
            : `Request failed with status ${response.status}.`,
        retriable:
          typeof parsed.retriable === "boolean"
            ? parsed.retriable
            : response.status === 429 || response.status >= 500,
        requestId:
          typeof parsed.request_id === "string" && parsed.request_id.length > 0
            ? parsed.request_id
            : headerRequestId,
        retryAfterSeconds,
        details: Array.isArray(parsed.details) ? parsed.details : null,
      });
    }

    throw new ApiClientError({
      status: response.status,
      errorCode: "http_error",
      message: `Request failed with HTTP status ${response.status}.`,
      retriable: response.status === 429 || response.status >= 500,
      requestId: headerRequestId,
      retryAfterSeconds,
      details: null,
    });
  }

  if (parsed === null) {
    throw new ApiClientError({
      status: response.status,
      errorCode: "invalid_json",
      message: "Received malformed JSON response from server.",
      retriable: false,
      requestId: headerRequestId,
    });
  }

  return parsed as T;
}

export async function fetchMarkets(signal?: AbortSignal): Promise<MarketsResponse> {
  const base = resolveApiBaseUrl();
  return requestJson<MarketsResponse>(`${base}/api/v1/markets`, {
    method: "GET",
    cache: "no-store",
    signal,
  });
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const base = resolveApiBaseUrl();
  const healthUrl = base ? `${base}/health` : "/api/health";
  return requestJson<HealthResponse>(healthUrl, {
    method: "GET",
    cache: "no-store",
    signal,
  });
}

export async function sendChatTurn(
  payload: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const sanitizedBudget = sanitizeOutgoingMaxBudget(payload.max_budget);
  const bodyPayload: ChatRequest = {
    ...payload,
    ...(sanitizedBudget !== undefined ? { max_budget: sanitizedBudget } : {}),
  };
  const base = resolveApiBaseUrl();
  return requestJson<ChatResponse>(`${base}/api/v1/chat`, {
    method: "POST",
    body: JSON.stringify(bodyPayload),
    signal,
  });
}

export async function searchOffers(
  payload: SearchRequest,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const sanitizedBudget = sanitizeOutgoingMaxBudget(payload.max_budget);
  const bodyPayload: SearchRequest = {
    ...payload,
    ...(sanitizedBudget !== undefined ? { max_budget: sanitizedBudget } : {}),
  };
  const base = resolveApiBaseUrl();
  return requestJson<SearchResponse>(`${base}/api/v1/search`, {
    method: "POST",
    body: JSON.stringify(bodyPayload),
    signal,
  });
}
