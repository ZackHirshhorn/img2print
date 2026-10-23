// App state. Settings and a few preferences survive a reload; uploads and models live on the server.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { DEFAULT_SETTINGS, type BuiltModel, type Settings, type Upload } from "./api/client";

export type SizeKey = "width" | "height" | "longest";

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

  setSettings: (patch: Partial<Settings>) => void;
  setSize: (key: SizeKey, mm: number) => void;
  setMaterial: (material: string) => void;
  setAutoBuild: (on: boolean) => void;
  setUpload: (upload: Upload, file: File) => void;
  setModel: (model: BuiltModel | null) => void;
  togglePart: (name: string) => void;
  setExplode: (mm: number) => void;
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

      setSettings: (patch) => set({ settings: { ...get().settings, ...patch } }),
      setSize: (key, mm) =>
        set({ settings: { ...get().settings, width: null, height: null, longest: null, [key]: mm } }),
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
  return ["width", 100];
}
