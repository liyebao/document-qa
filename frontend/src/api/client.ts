export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "请求失败，请重试";
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function request<T>(
  path: string,
  { timeoutMs = 240000, ...options }: RequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      let code = "HTTP_ERROR";
      let message = `请求失败（${response.status}）`;
      try {
        const body = (await response.json()) as {
          error?: { code?: string; message?: string };
        };
        if (body.error?.code) {
          code = body.error.code;
        }
        if (body.error?.message) {
          message = body.error.message;
        }
      } catch {
        // 非 JSON 错误响应使用默认提示
      }
      throw new ApiError(response.status, code, message);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "TIMEOUT", "请求超时，请重试");
    }
    throw new ApiError(0, "NETWORK_ERROR", "网络异常，请检查后端服务是否启动");
  } finally {
    window.clearTimeout(timer);
  }
}
