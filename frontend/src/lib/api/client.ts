import { storage } from "../storage";

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
  requiresAuth?: boolean;
  retries?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface BinaryRequestOptions {
  method?: HttpMethod;
  body?: unknown;
  requiresAuth?: boolean;
  retries?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
}

interface ErrorShape {
  detail?: string;
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(message: string, status: number, code = "request_failed", details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shouldRetry(status: number): boolean {
  return [502, 503, 504].includes(status);
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

export class ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const {
      method = "GET",
      body,
      requiresAuth = true,
      retries = 1,
      timeoutMs = 30000,
      signal,
    } = options;

    let lastError: unknown;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      const abortFromCaller = () => controller.abort();

      if (signal?.aborted) {
        controller.abort();
      } else {
        signal?.addEventListener("abort", abortFromCaller, { once: true });
      }

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };

        if (requiresAuth) {
          const token = storage.getTokenForCurrentPath();
          if (token) {
            headers.Authorization = `Bearer ${token}`;
          }
        }

        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });

        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);

        const contentType = response.headers.get("content-type") ?? "";
        const responseBody = contentType.includes("application/json")
          ? await response.json()
          : null;

        if (!response.ok) {
          const apiError = this.buildError(response.status, responseBody);
          if (shouldRetry(response.status) && attempt < retries) {
            await sleep(250 * (attempt + 1));
            continue;
          }
          throw apiError;
        }

        return responseBody as T;
      } catch (error) {
        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);
        lastError = error;

        const isAbortError = error instanceof DOMException && error.name === "AbortError";
        const abortedByCaller = Boolean(signal?.aborted);
        const isTransientNetworkError = error instanceof TypeError || (isAbortError && !abortedByCaller);

        if (abortedByCaller) {
          throw new ApiClientError("Request aborted.", 499, "request_aborted");
        }

        if (isTransientNetworkError && attempt < retries) {
          await sleep(250 * (attempt + 1));
          continue;
        }
      }
    }

    if (lastError instanceof ApiClientError) {
      throw lastError;
    }

    if (lastError instanceof DOMException && lastError.name === "AbortError") {
      throw new ApiClientError("Request timed out.", 504, "request_timeout");
    }

    throw new ApiClientError("Unable to reach the API service.", 503, "network_error");
  }

  async requestBlob(path: string, options: BinaryRequestOptions = {}): Promise<Response> {
    const {
      method = "GET",
      body,
      requiresAuth = true,
      retries = 1,
      timeoutMs = 30000,
      signal,
    } = options;

    let lastError: unknown;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      const abortFromCaller = () => controller.abort();

      if (signal?.aborted) {
        controller.abort();
      } else {
        signal?.addEventListener("abort", abortFromCaller, { once: true });
      }

      try {
        const headers: Record<string, string> = {};

        if (body !== undefined) {
          headers["Content-Type"] = "application/json";
        }

        if (requiresAuth) {
          const token = storage.getTokenForCurrentPath();
          if (token) {
            headers.Authorization = `Bearer ${token}`;
          }
        }

        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });

        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);

        if (!response.ok) {
          if (shouldRetry(response.status) && attempt < retries) {
            await sleep(250 * (attempt + 1));
            continue;
          }

          const contentType = response.headers.get("content-type") ?? "";
          const responseBody = contentType.includes("application/json") ? await response.json() : null;
          throw this.buildError(response.status, responseBody);
        }

        return response;
      } catch (error) {
        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);
        lastError = error;

        const isAbortError = error instanceof DOMException && error.name === "AbortError";
        const abortedByCaller = Boolean(signal?.aborted);
        const isTransientNetworkError = error instanceof TypeError || (isAbortError && !abortedByCaller);

        if (abortedByCaller) {
          throw new ApiClientError("Request aborted.", 499, "request_aborted");
        }

        if (isTransientNetworkError && attempt < retries) {
          await sleep(250 * (attempt + 1));
          continue;
        }
      }
    }

    if (lastError instanceof ApiClientError) {
      throw lastError;
    }

    if (lastError instanceof DOMException && lastError.name === "AbortError") {
      throw new ApiClientError("Request timed out.", 504, "request_timeout");
    }

    throw new ApiClientError("Unable to reach the API service.", 503, "network_error");
  }

  async requestForm<T>(path: string, formData: FormData, options: Omit<RequestOptions, "body"> = {}): Promise<T> {
    const {
      method = "POST",
      requiresAuth = true,
      retries = 1,
      timeoutMs = 30000,
      signal,
    } = options;

    let lastError: unknown;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      const abortFromCaller = () => controller.abort();

      if (signal?.aborted) {
        controller.abort();
      } else {
        signal?.addEventListener("abort", abortFromCaller, { once: true });
      }

      try {
        const headers: Record<string, string> = {};

        if (requiresAuth) {
          const token = storage.getTokenForCurrentPath();
          if (token) {
            headers.Authorization = `Bearer ${token}`;
          }
        }

        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: formData,
          signal: controller.signal,
        });

        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);

        const contentType = response.headers.get("content-type") ?? "";
        const responseBody = contentType.includes("application/json")
          ? await response.json()
          : null;

        if (!response.ok) {
          const apiError = this.buildError(response.status, responseBody);
          if (shouldRetry(response.status) && attempt < retries) {
            await sleep(250 * (attempt + 1));
            continue;
          }
          throw apiError;
        }

        return responseBody as T;
      } catch (error) {
        window.clearTimeout(timeout);
        signal?.removeEventListener("abort", abortFromCaller);
        lastError = error;

        const isAbortError = error instanceof DOMException && error.name === "AbortError";
        const abortedByCaller = Boolean(signal?.aborted);
        const isTransientNetworkError = error instanceof TypeError || (isAbortError && !abortedByCaller);

        if (abortedByCaller) {
          throw new ApiClientError("Request aborted.", 499, "request_aborted");
        }

        if (isTransientNetworkError && attempt < retries) {
          await sleep(250 * (attempt + 1));
          continue;
        }
      }
    }

    if (lastError instanceof ApiClientError) {
      throw lastError;
    }

    if (lastError instanceof DOMException && lastError.name === "AbortError") {
      throw new ApiClientError("Request timed out.", 504, "request_timeout");
    }

    throw new ApiClientError("Unable to reach the API service.", 503, "network_error");
  }

  get<T>(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  postForm<T>(path: string, formData: FormData, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return this.requestForm<T>(path, formData, { ...options, method: "POST" });
  }

  patch<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  delete<T>(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  requestBlobBody(path: string, options?: Omit<BinaryRequestOptions, "method" | "body"> & { body?: unknown }): Promise<Response> {
    return this.requestBlob(path, { ...options, method: "POST" });
  }

  private buildError(status: number, responseBody: unknown): ApiClientError {
    const payload = (responseBody as ErrorShape) ?? {};

    if (typeof payload.detail === "string") {
      return new ApiClientError(payload.detail, status, "request_failed");
    }

    if (typeof payload.message === "string" && typeof payload.code === "string") {
      return new ApiClientError(payload.message, status, payload.code, payload.details);
    }

    return new ApiClientError("Request failed.", status, "request_failed");
  }
}

const baseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const apiClient = new ApiClient(baseUrl);
