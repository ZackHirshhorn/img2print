// Texts on the design: what they say, their font, and how they stand apart (colour, raised or cut in).
import { useQuery } from "@tanstack/react-query";
import { api, type Font, type TextItem } from "../api/client";
import { useStore } from "../store";
import { useTrace } from "../useTrace";
import { FontPicker, hasHebrew } from "./FontPicker";
import { NumberField, Segmented, Toggle } from "./fields";

const STYLE_HINTS: Record<string, string> = {
  paint: "Flush with the surface, set apart by its colour.",
  emboss: "Stands out of the surface. Without a colour of its own, it is the colour under it.",
  engrave: "Cut into the surface. With a colour, the bottom of each letter shows it.",
};
const LAYER_HINT = " By layers: text in its own colour gets the top layer, so it stands a layer above the rest.";
const SURFACE = "";   // the colour select's value for "same as the surface"

export function TextPanel() {
  const texts = useStore((s) => s.settings.texts);
  const selected = useStore((s) => s.selectedText);
  const selectText = useStore((s) => s.selectText);
  const addText = useStore((s) => s.addText);
  const removeText = useStore((s) => s.removeText);
  const upload = useStore((s) => s.upload);

  return (
    <>
      {texts.length > 0 && (
        <ul className="text-list">
          {texts.map((t, i) => (
            <li key={i} className={selected === i ? "on" : ""}>
              <button type="button" className="text-pick" onClick={() => selectText(selected === i ? null : i)}>
                <span className="chip" style={{ background: t.color ?? "transparent" }} />
                <span dir="auto">{t.text.trim() || "(empty)"}</span>
              </button>
              <button type="button" className="link" aria-label="Remove this text" title="Remove"
                onClick={() => removeText(i)}>✕</button>
            </li>
          ))}
        </ul>
      )}
      {selected !== null && texts[selected] && <TextEditor index={selected} />}
      <button type="button" onClick={() => addText({ text: "טקסט" })} disabled={!upload}>Add text</button>
      {!upload && <p className="muted small">Add a file or start a blank plate first.</p>}
    </>
  );
}

function TextEditor({ index }: { index: number }) {
  const t = useStore((s) => s.settings.texts[index]);
  const stacking = useStore((s) => s.settings.stacking);
  const setText = useStore((s) => s.setText);
  const traced = useTrace();
  const set = (patch: Partial<TextItem>) => setText(index, patch);
  const error = traced.data?.trace.texts?.[index]?.error;
  const layers = traced.data?.trace.layers ?? [];
  const known = layers.some((l) => t.color && sameColor(l.color, t.color));

  function pickFont(family: string, font: Font | undefined) {
    const weights = (font?.variants ?? []).filter((v) => !v.endsWith("i")).map(Number);
    const weight = weights.length && !weights.includes(t.weight)
      ? weights.reduce((a, b) => (Math.abs(b - t.weight) < Math.abs(a - t.weight) ? b : a))
      : t.weight;
    set({ font: family, weight, italic: t.italic && !!font?.variants.includes(`${weight}i`) });
  }

  return (
    <div className="text-editor">
      <textarea
        dir="auto"
        rows={Math.min(4, t.text.split("\n").length + 1)}
        value={t.text}
        onChange={(e) => set({ text: e.target.value })}
        aria-label="Text"
        placeholder="Your text"
      />
      {error && <p className="error small">{error}</p>}

      <label className="field">
        <span className="field-label">Font</span>
        <FontPicker value={t.font} onChange={pickFont} hebrew={hasHebrew(t.text)} />
      </label>
      <WeightSelect text={t} onChange={set} />

      <NumberField label="Letter height" value={t.size} onChange={(size) => set({ size })} step={0.5} min={0.5} unit="mm" />

      <Segmented
        label="How the text stands apart"
        value={t.style}
        options={[
          { value: "paint", label: "Colour" },
          { value: "emboss", label: "Raised" },
          { value: "engrave", label: "Engraved" },
        ]}
        onChange={(style) => set(style === "paint" && t.color === null ? { style, color: "black" } : { style })}
      />
      <p className="muted hint">{STYLE_HINTS[t.style]}{stacking === "layers" && t.color !== null ? LAYER_HINT : ""}</p>
      {t.style !== "paint" && (
        <NumberField label={t.style === "emboss" ? "Stands out" : "Cut depth"} value={t.depth}
          onChange={(depth) => set({ depth })} step={0.1} min={0.1} unit="mm" />
      )}

      <label className="field">
        <span className="field-label">Colour</span>
        <span className="row">
          <select
            value={t.color === null ? SURFACE : known ? layers.find((l) => sameColor(l.color, t.color!))!.color : "custom"}
            onChange={(e) => set({ color: e.target.value === SURFACE ? null : e.target.value === "custom" ? "#d42a1f" : e.target.value })}
          >
            {t.style !== "paint" && <option value={SURFACE}>Same as the surface</option>}
            {layers.map((l) => <option key={l.name} value={l.color}>{l.name} (from the design)</option>)}
            <option value="custom">Another colour…</option>
          </select>
          {t.color !== null && !known && (
            <input type="color" aria-label="Text colour" value={toHex6(t.color)}
              onChange={(e) => set({ color: e.target.value })} />
          )}
        </span>
      </label>

      <details className="text-more">
        <summary>Position and spacing</summary>
        <NumberField label="Across (from the left)" value={Math.round(t.x * 1000) / 10}
          onChange={(v) => set({ x: v / 100 })} step={1} unit="%" />
        <NumberField label="Down (from the top)" value={Math.round(t.y * 1000) / 10}
          onChange={(v) => set({ y: v / 100 })} step={1} unit="%" />
        <NumberField label="Rotation" value={t.rotation} onChange={(rotation) => set({ rotation })} step={5} unit="°" />
        {t.text.includes("\n") && (
          <>
            <Segmented
              label="Line alignment"
              value={t.align}
              options={[
                { value: "right", label: "Right" },
                { value: "center", label: "Centre" },
                { value: "left", label: "Left" },
              ]}
              onChange={(align) => set({ align })}
            />
            <NumberField label="Line spacing" value={t.line_spacing}
              onChange={(line_spacing) => set({ line_spacing })} step={0.1} min={0.1} unit="×" />
          </>
        )}
        <NumberField label="Letter spacing" value={t.letter_spacing}
          onChange={(letter_spacing) => set({ letter_spacing })} step={0.1} unit="mm" />
      </details>
    </div>
  );
}

function WeightSelect({ text, onChange }: { text: TextItem; onChange: (p: Partial<TextItem>) => void }) {
  const fonts = useFonts();
  const font = fonts?.find((f) => f.family === text.font);
  const variants = font?.variants ?? ["400", "700"];
  const weights = [...new Set(variants.map((v) => parseInt(v, 10)))].sort((a, b) => a - b);
  const italic = variants.includes(`${text.weight}i`);
  return (
    <div className="row">
      <label className="field grow">
        <span className="field-label">Weight</span>
        <select value={text.weight} onChange={(e) => onChange({ weight: Number(e.target.value) })}>
          {(weights.includes(text.weight) ? weights : [...weights, text.weight].sort((a, b) => a - b)).map((w) => (
            <option key={w} value={w}>{WEIGHT_NAMES[w] ?? w}</option>
          ))}
        </select>
      </label>
      {(italic || text.italic) && (
        <Toggle label="Italic" checked={text.italic} onChange={(v) => onChange({ italic: v })} />
      )}
    </div>
  );
}

function useFonts() {
  return useQuery({ queryKey: ["fonts"], queryFn: api.fonts, staleTime: Infinity }).data;
}

const WEIGHT_NAMES: Record<number, string> = {
  100: "Thin", 200: "Extra light", 300: "Light", 400: "Regular", 500: "Medium",
  600: "Semi-bold", 700: "Bold", 800: "Extra bold", 900: "Black",
};

function sameColor(a: string, b: string): boolean {
  return toHex6(a) === toHex6(b);
}

const NAMED: Record<string, string> = { black: "#000000", white: "#ffffff", red: "#e02020" };

/** "#rrggbb" for the colour input; names it does not know fall back to black. */
function toHex6(c: string): string {
  const v = (NAMED[c.trim().toLowerCase()] ?? c).trim();
  if (/^#[0-9a-f]{6}$/i.test(v)) return v.toLowerCase();
  if (/^#[0-9a-f]{3}$/i.test(v)) return `#${[...v.slice(1)].map((ch) => ch + ch).join("")}`.toLowerCase();
  return "#000000";
}
