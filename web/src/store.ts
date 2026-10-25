// App state. Settings and a few preferences survive a reload; uploads and models live on the server.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { DEFAULT_SETTINGS, DEFAULT_TEXT, type BuiltModel, type Settings, type TextItem, type Upload } from "./api/client";

/** "fit": no size given, so a shape's design fits its face. */
export type SizeKey = "width" | "height" | "longest" | "fit";
export type View = "design" | "3d";

interface State {
  settings: Settings;
  material: string;
  autoBuild: boolean;
  upload: Upload | null;
  /** Object URL of the uploaded file, for the thumbnail. */
  previewUrl: string | null;
  model: BuiltModel | null;
  hidden: string[];
  explode: number;
  view: View;
  /** Index into settings.texts of the text being edited. */
  selectedText: number | null;

  setSettings: (patch: Partial<Settings>) => void;
  setSize: (key: SizeKey, mm: number) => void;
  setMaterial: (material: string) => void;
  setAutoBuild: (on: boolean) => void;
  setUpload: (upload: Upload, file: File) => void;
  setModel: (model: BuiltModel | null) => void;
  togglePart: (name: string) => void;
  setExplode: (mm: number) => void;
  setView: (view: View) => void;
  addText: (patch?: Partial<TextItem>) => void;
  setText: (index: number, patch: Partial<TextItem>) => void;
  removeText: (index: number) => void;
  selectText: (index: number | null) => void;
}

export const useStore = create<State>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      material: "PLA",
      autoBuild: false,
      upload: null,
      previewUrl: null,
      model: null,
      hidden: [],
      explode: 0,
      view: "design",
      selectedText: null,

      setSettings: (patch) => set({ settings: { ...get().settings, ...patch } }),
      setSize: (key, mm) => {
        const size = { width: null, height: null, longest: null };
        set({ settings: { ...get().settings, ...size, ...(key === "fit" ? {} : { [key]: mm }) } });
      },
      setMaterial: (material) => set({ material }),
      setAutoBuild: (autoBuild) => set({ autoBuild }),
      setUpload(upload, file) {
        const old = get().previewUrl;
        if (old) URL.revokeObjectURL(old);
        set({
          upload,
          previewUrl: URL.createObjectURL(file),
          model: null,
          hidden: [],
          settings: { ...get().settings, page: 1 },
        });
      },
      setModel: (model) => set({ model }),
      togglePart: (name) => {
        const hidden = get().hidden;
        set({ hidden: hidden.includes(name) ? hidden.filter((n) => n !== name) : [...hidden, name] });
      },
      setExplode: (explode) => set({ explode }),
      setView: (view) => set({ view }),
      addText(patch = {}) {
        const s = get().settings;
        const last = s.texts[s.texts.length - 1];
        // A new text starts in the font and colour of the last one, a little lower.
        const text: TextItem = last
          ? { ...DEFAULT_TEXT, font: last.font, weight: last.weight, style: last.style, color: last.color,
              depth: last.depth, size: last.size, y: Math.min(last.y + 0.2, 0.9), ...patch }
          : { ...DEFAULT_TEXT, ...patch };
        set({ settings: { ...s, texts: [...s.texts, text] }, selectedText: s.texts.length, view: "design" });
      },
      setText(index, patch) {
        const s = get().settings;
        set({ settings: { ...s, texts: s.texts.map((t, i) => (i === index ? { ...t, ...patch } : t)) } });
      },
      removeText(index) {
        const s = get().settings;
        const texts = s.texts.filter((_, i) => i !== index);
        const sel = get().selectedText;
        set({
          settings: { ...s, texts },
          selectedText: sel === null || sel < index ? sel : sel === index ? null : sel - 1,
        });
      },
      selectText: (selectedText) => set({ selectedText }),
    }),
    {
      name: "img2print",
      partialize: (s) => ({
        settings: s.settings,
        material: s.material,
        autoBuild: s.autoBuild,
      }),
      // Settings saved by an older version get any new options from the defaults, and lose the
      // ones the app no longer offers (removed options, the black-and-white mode, raised colours).
      // The app always opens on "Find colours", whatever was picked last time.
      merge: (saved, current) => {
        const s = saved as Partial<State> | undefined;
        const known = Object.entries(s?.settings ?? {}).filter(([k]) => k in DEFAULT_SETTINGS);
        const settings: Settings = { ...DEFAULT_SETTINGS, ...Object.fromEntries(known), raised: false };
        settings.colors ??= DEFAULT_SETTINGS.colors;
        settings.palette = null;
        settings.texts = (settings.texts ?? []).map((t) => ({ ...DEFAULT_TEXT, ...t }));
        return { ...current, ...s, settings };
      },
    },
  ),
);

export function sizeOf(settings: Settings): [SizeKey, number] {
  for (const key of ["width", "height", "longest"] as const) {
    const v = settings[key];
    if (v != null) return [key, v];
  }
  return settings.recipe === "shape" ? ["fit", 100] : ["width", 100];
}
