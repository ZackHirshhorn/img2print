// Every option of the print job, grouped like the command line's help.
import { useEffect, useState } from "react";
import { DEFAULT_SETTINGS } from "../api/client";
import { sizeOf, useStore, type SizeKey } from "../store";
import { NumberField, Section, Segmented } from "./fields";

const STACKING_HINTS: Record<string, string> = {
  full: "Every colour runs through the whole plaque.",
  top: "A plain base in one filament, with the whole design only in the top layer.",
  layers: "A base in the background colour, with the other colours in a layer on top.",
};

export function SettingsPanel() {
  const s = useStore((st) => st.settings);
  const set = useStore((st) => st.setSettings);
  const setSize = useStore((st) => st.setSize);
  const [sizeKey, sizeMm] = sizeOf(s);

  return (
    <div className="settings">
      <Section title="Size">
        <div className="row">
          <select
            aria-label="Which side to size"
            value={sizeKey}
            onChange={(e) => setSize(e.target.value as SizeKey, sizeMm)}
          >
            <option value="width">Width</option>
            <option value="height">Height</option>
            <option value="longest">Longest side</option>
          </select>
          <NumberField label="" value={sizeMm} onChange={(v) => setSize(sizeKey, v)} step={1} min={1} unit="mm" />
        </div>
        <NumberField label="Padding (blank border, inside the size)" value={s.padding}
          onChange={(padding) => set({ padding })} step={1} min={0} unit="mm" />
      </Section>

      <Section title="Colours">
        <ColourOptions />
      </Section>

      <Section title="Style">
        <Segmented
          label="How the colours are stacked"
          value={s.stacking}
          options={[
            { value: "full", label: "Full depth" },
            { value: "top", label: "Top only" },
            { value: "layers", label: "By layers" },
          ]}
          onChange={(stacking) => set({ stacking })}
        />
        <p className="muted hint">{STACKING_HINTS[s.stacking]}</p>
        {s.stacking === "full" && (
          <NumberField label="Plaque thickness" value={s.thickness} onChange={(thickness) => set({ thickness })}
            step={0.1} min={0.01} unit="mm" />
        )}
        {s.stacking === "top" && (
          <label className="field">
            <span className="field-label">Base colour</span>
            <input
              type="text"
              placeholder="white, grey, #d42a1f"
              defaultValue={s.base_color}
              key={s.base_color}
              onBlur={(e) => set({ base_color: e.target.value.trim() || DEFAULT_SETTINGS.base_color })}
            />
          </label>
        )}
        {s.stacking !== "full" && (
          <>
            <NumberField label="Base" value={s.base} onChange={(base) => set({ base })} step={0.1} min={0.01} unit="mm" />
            <NumberField label={s.stacking === "top" ? "Coloured top" : "Colour layer"} value={s.layer}
              onChange={(layer) => set({ layer })} step={0.1} min={0.01} unit="mm" />
          </>
        )}
        <NumberField label="Corner radius" value={s.corner_radius}
          onChange={(corner_radius) => set({ corner_radius })} step={1} min={0} unit="mm" />
      </Section>

      <details className="section advanced">
        <summary>Advanced</summary>
        <NumberField label="Edge smoothing" value={s.smooth} onChange={(smooth) => set({ smooth })}
          step={0.1} min={0} unit="px" />
        <NumberField label="Drop specks under" value={s.min_area} onChange={(min_area) => set({ min_area })}
          step={0.01} min={0} unit="mm²" />
        <NumberField label="Simplify edges" value={s.simplify} onChange={(simplify) => set({ simplify })}
          step={0.01} min={0} unit="mm" />
      </details>
    </div>
  );
}

function ColourOptions() {
  const s = useStore((st) => st.settings);
  const set = useStore((st) => st.setSettings);
  const byPalette = s.palette != null;

  return (
    <>
      <Segmented
        label="How to pick colours"
        value={byPalette ? "palette" : "count"}
        options={[
          { value: "count", label: "Find colours" },
          { value: "palette", label: "My filaments" },
        ]}
        onChange={(v) =>
          set(v === "count"
            ? { palette: null, colors: s.colors ?? 3 }
            : { colors: null, palette: s.palette ?? ["white", "black", "red"] })
        }
      />
      {byPalette ? (
        <TextList
          label="Filament colours"
          hint="comma separated: white, black, #d42a1f"
          value={s.palette ?? []}
          onChange={(palette) => palette.length >= 2 && set({ palette })}
        />
      ) : (
        <NumberField label="Colours, background included" value={s.colors ?? 3}
          onChange={(colors) => set({ colors })} step={1} min={2} max={16} integer />
      )}
      <label className="field">
        <span className="field-label">Background colour</span>
        <input
          type="text"
          placeholder="auto (the colour around the edge)"
          defaultValue={s.background ?? ""}
          key={s.background ?? ""}
          onBlur={(e) => set({ background: e.target.value.trim() || null })}
        />
      </label>
    </>
  );
}

/** A comma separated list, applied when you leave the field. */
function TextList({ label, hint, value, onChange }: {
  label: string;
  hint: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  useEffect(() => setText(joined), [joined]);
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        type="text"
        value={text}
        placeholder={hint}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onChange(text.split(",").map((c) => c.trim()).filter(Boolean))}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
    </label>
  );
}
