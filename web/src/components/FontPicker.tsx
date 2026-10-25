// Choose a font family: bundled, your own, or any of Google Fonts, each shown in its own letters.
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fontFileUrl, type Font } from "../api/client";

const MAX_LISTED = 150;
const HEBREW = /[֐-׿]/;

export function FontPicker({ value, onChange, hebrew }: {
  value: string;
  onChange: (family: string, font: Font | undefined) => void;
  /** The text being set has Hebrew: start with Hebrew fonts only. */
  hebrew: boolean;
}) {
  const fonts = useQuery({ queryKey: ["fonts"], queryFn: api.fonts, staleTime: Infinity });
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [hebrewOnly, setHebrewOnly] = useState(hebrew);
  const [category, setCategory] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const current = fonts.data?.find((f) => f.family === value);
  usePreviewFont(current);

  useEffect(() => setHebrewOnly(hebrew), [hebrew]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const categories = useMemo(
    () => [...new Set((fonts.data ?? []).map((f) => f.category).filter(Boolean))].sort(),
    [fonts.data],
  );
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (fonts.data ?? [])
      .filter((f) => (!hebrewOnly || f.subsets.includes("hebrew"))
        && (!category || f.category === category)
        && (!q || f.family.toLowerCase().includes(q)))
      .sort((a, b) => rank(a) - rank(b));
  }, [fonts.data, search, hebrewOnly, category]);

  return (
    <div className="font-picker" ref={box}>
      <button type="button" className="font-current" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span style={{ fontFamily: previewFamily(value) }}>{value}</span>
        <span className="muted">▾</span>
      </button>
      {open && (
        <div className="font-menu" role="dialog" aria-label="Choose a font">
          <input
            type="search"
            placeholder={`Search ${fonts.data?.length ?? ""} fonts`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
          <div className="row">
            <label className="toggle">
              <input type="checkbox" checked={hebrewOnly} onChange={(e) => setHebrewOnly(e.target.checked)} />
              <span>Hebrew</span>
            </label>
            <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All styles</option>
              {categories.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          {fonts.isPending && <p className="muted small">Loading fonts…</p>}
          {fonts.isError && <p className="error small">{fonts.error.message}</p>}
          <ul className="font-list">
            {matches.slice(0, MAX_LISTED).map((f) => (
              <FontRow key={f.family} font={f} selected={f.family === value}
                onPick={() => { onChange(f.family, f); setOpen(false); }} />
            ))}
          </ul>
          {matches.length > MAX_LISTED && (
            <p className="muted small">{matches.length - MAX_LISTED} more: type to narrow the list.</p>
          )}
          {fonts.data && matches.length === 0 && <p className="muted small">No font matches.</p>}
          <AddFont onAdded={(f) => { onChange(f.family, f); setOpen(false); }} />
        </div>
      )}
    </div>
  );
}

/** Bundled and your own fonts first, then Google's by popularity. */
function rank(f: Font): number {
  return f.source === "google" ? f.popularity || 99999 : -1;
}

function FontRow({ font, selected, onPick }: { font: Font; selected: boolean; onPick: () => void }) {
  const row = useRef<HTMLLIElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = row.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true));
    io.observe(el);
    return () => io.disconnect();
  }, []);
  usePreviewFont(visible ? font : undefined);
  const sample = font.subsets.includes("hebrew") ? "אבג" : "";

  return (
    <li ref={row}>
      <button type="button" className={selected ? "on" : ""} onClick={onPick}>
        <span style={{ fontFamily: visible ? previewFamily(font.family) : undefined }}>
          {font.family} {sample}
        </span>
        <span className="muted small">{font.source === "google" ? font.category : font.source}</span>
      </button>
    </li>
  );
}

function AddFont({ onAdded }: { onAdded: (f: Font) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const add = useMutation({
    mutationFn: api.addFont,
    onSuccess: (f) => {
      client.invalidateQueries({ queryKey: ["fonts"] });
      onAdded(f);
    },
  });
  return (
    <div className="add-font">
      <button type="button" className="link" onClick={() => input.current?.click()} disabled={add.isPending}>
        {add.isPending ? "Adding…" : "Add a font file (TTF, OTF, WOFF)…"}
      </button>
      <input ref={input} type="file" accept=".ttf,.otf,.woff,.woff2" hidden
        onChange={(e) => e.target.files?.[0] && add.mutate(e.target.files[0])} />
      {add.isError && <p className="error small">{add.error.message}</p>}
    </div>
  );
}

// --- showing a family in its own letters -------------------------------------------------------

const loaded = new Set<string>();

const previewFamily = (family: string) => `"img2print ${family}", system-ui`;

/** Load a font for display, once: Google fonts only with the letters the picker shows, others whole. */
function usePreviewFont(font: Font | undefined) {
  useEffect(() => {
    if (!font || loaded.has(font.family)) return;
    loaded.add(font.family);
    const weight = font.variants.includes("400") ? 400 : parseInt(font.variants[0] ?? "400", 10);
    const url = font.source === "google" ? googleCssFontUrl(font, weight) : Promise.resolve(fontFileUrl(font.family, weight));
    url.then((u) => new FontFace(`img2print ${font.family}`, `url(${u})`).load())
      .then((face) => document.fonts.add(face))
      .catch(() => loaded.delete(font.family));
  }, [font]);
}

/** The subset file Google serves for just the picker's letters (a few kB). */
async function googleCssFontUrl(font: Font, weight: number): Promise<string> {
  const text = `${font.family} אבג`;
  const css = await fetch(`https://fonts.googleapis.com/css2?${new URLSearchParams({
    family: `${font.family}:wght@${weight}`,
    text: [...new Set(text)].join(""),
  })}`).then((r) => r.text());
  const url = /url\(([^)]+)\)/.exec(css)?.[1];
  if (!url) throw new Error("no font file");
  return url;
}

export const hasHebrew = (s: string) => HEBREW.test(s);
