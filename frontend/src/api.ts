export type User = {
  id: number;
  display_name: string;
  email: string;
  role: "ADMIN" | "INSPECTOR";
  organization: { name: string; timezone: string };
  csrf_token: string;
};
export type Group = {
  qty: number;
  expiry_state: "KNOWN" | "UNKNOWN";
  input_value?: string;
  normalized_date?: string;
  precision?: string;
  policy?: string;
  source?: "MANUAL" | "OCR";
  unknown_reason?: string | null;
  confirmed?: boolean;
  month_end_confirmed?: boolean;
};
export type Item = {
  id: number;
  name: string;
  unit: string;
  required_qty: number;
  requires_expiry: boolean;
  actual_qty: number | null;
  checked_at: string | null;
  groups: Group[];
  shortage_qty?: number;
  expired_qty?: number;
  unknown_qty?: number;
  eligible_qty?: number;
  replenish_qty?: number;
  reasons?: string[];
};
export type Template = {
  id: number;
  name: string;
  version: number;
  items: Item[];
};
export type Kit = {
  id: number;
  name: string;
  location: string;
  public_code: string;
  interval_days: number;
  archived: boolean;
  template_id: number;
  template_name: string;
  template_version: number;
  last_result: string;
  freshness: string;
  warnings: string[];
  due_date: string | null;
  last_completed_at: string | null;
  draft_id: number | null;
  draft_owner_id: number | null;
  draft_revision: number | null;
};
export type Inspection = {
  id: number;
  kit_id: number;
  owner_id: number;
  lifecycle: string;
  revision: number;
  started_at: string;
  completed_at: string | null;
  inspection_date: string | null;
  result: string | null;
  snapshot: {
    organization_name: string;
    kit_name: string;
    location: string;
    inspector_name: string;
    timezone: string;
    interval_days: number;
    template_id: number;
    template_name: string;
    template_version: number;
  };
  items: Item[];
  cancellation_reason: string | null;
};
export type History = { items: Inspection[]; page: number; has_next: boolean };
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
let csrf = "";
export function setCSRF(value: string) {
  csrf = value;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body:
        body instanceof FormData
          ? body
          : body
            ? JSON.stringify(body)
            : undefined,
    });
  } catch {
    throw new ApiError(
      "NETWORK_ERROR",
      "Нет связи с сервером. Изменения не подтверждены. Проверьте подключение и повторите сохранение.",
      0,
    );
  }
  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ message: "Не удалось выполнить действие." }));
    if (res.status === 401 && path !== "/auth/login" && csrf)
      window.dispatchEvent(new Event("medkit-session-expired"));
    throw new ApiError(
      error.code,
      error.message +
        (error.field_errors?.length
          ? " " +
            error.field_errors
              .map(
                (f: { field: string; message: string }) =>
                  `${f.field}: ${f.message}`,
              )
              .join("; ")
          : ""),
      res.status,
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
export const dateLabel = (value: string | null) =>
  value
    ? new Date(
        value.length === 10 ? `${value}T12:00:00` : value,
      ).toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "Ещё не проверяли";
export const reasons: Record<string, string> = {
  SHORTAGE: "Недостача",
  EXPIRED: "Просрочено",
  EXPIRY_UNKNOWN: "Срок не установлен",
};
