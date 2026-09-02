export interface TraceStep {
  name: string;
  status: "completed" | "failed";
  summary: string;
  duration_ms: number;
}

export interface AnalysisResult {
  run_id: string;
  question: string;
  route: string;
  answer: string;
  sql: string;
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
  chart: null | {
    title: string;
    value_label: string;
    points: Array<{ label: string; value: number }>;
  };
  verification: { passed: boolean; checks: string[] };
  trace: TraceStep[];
  metrics: Record<string, number>;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly fallbackAvailable: boolean;

  constructor(message: string, code = "request_failed", fallbackAvailable = true) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.fallbackAvailable = fallbackAvailable;
  }
}

const REQUEST_TIMEOUT_MS = 25_000;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

async function parseError(response: Response): Promise<ApiRequestError> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string | { code?: string; message?: string; fallback_available?: boolean };
  } | null;
  const detail = payload?.detail;
  if (typeof detail === "string") {
    return new ApiRequestError(detail, "request_failed", response.status >= 429 || response.status >= 500);
  }
  return new ApiRequestError(
    detail?.message ?? `请求失败（HTTP ${response.status}）`,
    detail?.code ?? "request_failed",
    detail?.fallback_available ?? (response.status >= 429 || response.status >= 500),
  );
}

export async function analyze(question: string): Promise<AnalysisResult> {
  let response: Response;
  try {
    response = await fetchWithTimeout("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiRequestError("在线服务暂时不可用，已切换到预录制示例。", "network_error");
  }
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as AnalysisResult;
}
