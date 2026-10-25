// Typed wrappers around the img2print API. The types come from `npm run gen:api`.
import type { components } from "./schema";

type S = components["schemas"];
export type Settings = Required<S["Settings"]>;
export type Upload = S["Upload"];
export type Trace = S["Trace"];
export type BuiltModel = S["BuiltModel"];
export type PartStats = S["PartStats"];
export type Info = S["Info"];
export type Swatch = S["Swatch"];
export type TextItem = Required<S["Text"]>;
export type TextShape = S["TextShape"];
export type Font = S["Font"];

export const DEFAULT_SETTINGS: Settings = {
  recipe: "tile",
  width: 100,
  height: null,
  longest: null,
  stacking: "top",
  base: 1.2,
  layer: 0.8,
  thickness: 2,
  base_color: "white",
  corner_radius: 10,
  padding: 0,
  raised: false,
  shape: "box",
  shape_width: 40,
  shape_depth: 40,
  shape_height: 40,
  face: "top",
  threshold: 0.5,
  invert: false,
  colors: 2,
  palette: null,
  background: null,
  smooth: 0.6,
  min_area: 0.05,
  simplify: 0.02,
  page: 1,
  texts: [],
};

export const DEFAULT_TEXT: TextItem = {
  text: "",
  font: "Heebo",
  weight: 700,
  italic: false,
  size: 10,
  x: 0.5,
  y: 0.5,
  rotation: 0,
  align: "center",
  line_spacing: 1,
  letter_spacing: 0,
  style: "paint",
  color: "black",
  depth: 0.6,
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
  fonts: () => request<Font[]>("/api/fonts"),
  addFont(file: File): Promise<Font> {
    const form = new FormData();
    form.append("file", file);
    return request<Font>("/api/fonts", { method: "POST", body: form });
  },
};

export function fontFileUrl(family: string, weight = 400, italic = false): string {
  return `/api/fonts/file?${new URLSearchParams({ family, weight: String(weight), italic: String(italic) })}`;
}
