// Typed wrappers around the img2print API. The types come from `npm run gen:api`.
import type { components } from "./schema";

type S = components["schemas"];
export type Settings = Required<S["Settings"]>;
export type Upload = S["Upload"];
export type Trace = S["Trace"];
export type BuiltModel = S["BuiltModel"];
export type PartStats = S["PartStats"];
export type Info = S["Info"];
export type Preset = S["Preset"];
export type Swatch = S["Swatch"];

export const DEFAULT_SETTINGS: Settings = {
  recipe: "tile",
  width: 100,
  height: null,
  longest: null,
  base: 1.2,
  layer: 0.8,
  corner_radius: 10,
  raised: false,
  face_down: false,
  threshold: 0.5,
  invert: false,
  colors: null,
  palette: null,
  background: null,
  smooth: 0.6,
  min_area: 0.05,
  simplify: 0.02,
  page: 1,
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** FastAPI errors are {detail: string} or, for validation, {detail: [{msg}, ...]}. */
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => String((d as { msg?: string }).msg ?? d).replace(/^Value error, /, ""))
      .join("; ");
  }
  return `request failed (HTTP ${status})`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError("cannot reach the img2print server; is it running?", 0);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(body, res.status), res.status);
  return body as T;
}

function post<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export const api = {
  info: () => request<Info>("/api/info"),
  upload(file: File): Promise<Upload> {
    const form = new FormData();
    form.append("file", file);
    return request<Upload>("/api/uploads", { method: "POST", body: form });
  },
  trace: (upload_id: string, settings: Settings, signal?: AbortSignal) =>
    post<Trace>("/api/trace", { upload_id, settings }, signal),
  build: (upload_id: string, settings: Settings, material: string) =>
    post<BuiltModel>("/api/models", { upload_id, settings, material }),
};
