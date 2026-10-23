// Every option of the print job, grouped like the command line's help.
import { useEffect, useState } from "react";
import type { Info, Preset } from "../api/client";
import { sizeOf, useStore, type SizeKey } from "../store";
import { NumberField, Section, Segmented, Toggle } from "./fields";

/** Round to a whole number of layers (at least one), without float noise. */
const toLayers = (mm: number, layerHeight: number) =>
  Number((Math.max(1, Math.round(mm / layerHeight)) * layerHeight).toFixed(3));

export function SettingsPanel({ info }: { info: Info | undefined }) {
  const s = useStore((st) => st.settings);
  const set = useStore((st) => st.setSettings);
  const setSize = useStore((st) => st.setSize);
  const presetId = useStore((st) => st.presetId);
  const setPresetId = useStore((st) => st.setPresetId);
  const [sizeKey, sizeMm] = sizeOf(s);
  const preset: Preset | undefined = info?.presets.find((p) => p.id === presetId) ?? info?.presets[0];
  const step = preset?.layer_height ?? 0.1;

  function choosePreset(id: string) {
    const p = info?.presets.find((x) => x.id === id);
    if (!p) return;
    setPresetId(id);
    set({ base: toLayers(s.base, p.layer_height), layer: toLayers(s.layer, p.layer_height) });
  }

  const colourMode = s.colors != null || s.palette != null;

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
      </Section>

      <Section title="Mode">
        <Segmented
          label="Colour mode"
          value={colourMode ? "colour" : "two"}
          options={[
            { value: "two", label: "2 colours" },
            { value: "colour", label: "Colours" },
          ]}
          onChange={(v) =>
            set(v === "two" ? { colors: null, palette: null, background: null } : { colors: s.colors ?? 3 })
          }
        />
        {colourMode ? <ColourOptions /> : (
          <>
            <label className="field">
              <span className="field-label">Threshold <b>{s.threshold.toFixed(2)}</b></span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={s.threshold}
                onChange={(e) => set({ threshold: Number(e.target.value) })}
              />
            </label>
            <Toggle label="Invert (light parts become black)" checked={s.invert} onChange={(invert) => set({ invert })} />
          </>
        )}
      </Section>

      <Section title="Thickness">
        {info && (
          <label className="field">
            <span className="field-label">Printer</span>
            <select value={preset?.id} onChange={(e) => choosePreset(e.target.value)}>
              {info.presets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        )}
        <NumberField label="Base" value={s.base} onChange={(base) => set({ base })} step={step} min={0.01} unit="mm" />
        <NumberField label="Colour layer" value={s.layer} onChange={(layer) => set({ layer })}
          step={step} min={0.01} unit="mm" />
      </Section>

      <Section title="Style">
        <Toggle label="Raised (colours stand on a plain base)" checked={s.raised}
          onChange={(raised) => set({ raised })} />
        <Toggle label="Face down (print the design on the build plate)" checked={s.face_down}
          onChange={(face_down) => set({ face_down })} />
        <NumberField label="Corner radius" value={s.corner_radius}
          onChange={(corner_radius) => set({ corner_radius })} step={1} min={0} unit="mm" />
      </Section>

      <details className="section advanced">
        <summary>Advanced</summary>
        {colourMode && (
          <NumberField label="Edge smoothing" value={s.smooth} onChange={(smooth) => set({ smooth })}
            step={0.1} min={0} unit="px" />
        )}
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
        <span className="field-label">Base colour</span>
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
