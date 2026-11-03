import { t, locale } from "./i18n";
import { ElMessage } from "element-plus";

let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  quiet = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD"].includes(options.method))
    headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers,
      credentials: "same-origin",
    });
  } catch {
    if (!quiet) ElMessage.error(t("无法连接服务，请确认后端已启动"));
    throw new ApiError(0, t("无法连接服务"));
  }
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: t("服务暂不可用") }));
    const translated = t(error.message || "服务暂不可用");
    const message = error.details?.length
      ? `${translated}: ${error.details.map((x: { message: string }) => t(x.message)).join("; ")}`
      : locale.value === "en" && /\p{Script=Han}/u.test(translated)
        ? `Request failed (${response.status}). Please check your input or contact your administrator.`
        : translated;
    if (!quiet) ElMessage.error(message);
    throw new ApiError(response.status, message);
  }
  return response.json();
}
export function write<T>(
  path: string,
  body: unknown,
  etag?: string,
  method = "POST",
) {
  const headers: Record<string, string> = {
    "Idempotency-Key": crypto.randomUUID(),
  };
  if (etag) headers["If-Match"] = etag;
  return api<T>(path, { method, headers, body: JSON.stringify(body) });
}
