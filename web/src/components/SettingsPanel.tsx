// Every option of the print job, grouped like the command line's help.
import { useEffect, useState } from "react";
import { DEFAULT_SETTINGS } from "../api/client";
import { sizeOf, useStore, type SizeKey } from "../store";
import { NumberField, Section, Segmented } from "./fields";
import { TextPanel } from "./TextPanel";

const STACKING_HINTS: Record<string, string> = {
  full: "Every colour runs through the whole plaque.",
  top: "A plain base in one filament, with the whole design only in the top layer.",
  layers: "Colour by layer, for any printer: a base in the background colour, then each colour in its own "
    + "layer above the last. Pause and swap filament at the heights shown after the build.",
};

const SHAPE_STACKING_HINTS: Record<string, string> = {
  full: "Every colour runs right through the shape, to the opposite face.",
  top: "A plain body in one filament, with the whole face (background included) in the top layer.",
  layers: "Colour by layer: a body in the background colour, then each colour in its own layer standing "
    + "out of the face. Print with the face up; swap filament at the heights shown after the build.",
};

const FACES = ["top", "bottom", "front", "back", "left", "right"];

export function SettingsPanel() {
  const s = useStore((st) => st.settings);
  const set = useStore((st) => st.setSettings);
  const setSize = useStore((st) => st.setSize);
  const [sizeKey, sizeMm] = sizeOf(s);
  const onShape = s.recipe === "shape";

  return (
    <div className="settings">
      <Section title="Shape">
        <Segmented
          label="What to print"
          value={s.recipe}
          options={[
            { value: "tile", label: "Plaque" },
            { value: "shape", label: "On a shape" },
          ]}
          onChange={(recipe) => {
            set({ recipe });
            if (recipe === "shape") setSize("fit", sizeMm);   // the design fits the face to start with
          }}
        />
        {onShape && <ShapeOptions />}
      </Section>

      <Section title={onShape ? "Design size" : "Size"}>
        <div className="row">
          <select
            aria-label="Which side to size"
            value={sizeKey}
            onChange={(e) => setSize(e.target.value as SizeKey, sizeMm)}
          >
            {onShape && <option value="fit">Fit the face</option>}
            <option value="width">Width</option>
            <option value="height">Height</option>
            <option value="longest">Longest side</option>
          </select>
          {sizeKey !== "fit" && (
            <NumberField label="" value={sizeMm} onChange={(v) => setSize(sizeKey, v)} step={1} min={1} unit="mm" />
          )}
        </div>
        {(!onShape || sizeKey === "fit") && (
          <NumberField label={onShape ? "Margin around the design" : "Padding (blank border, inside the size)"}
            value={s.padding} onChange={(padding) => set({ padding })} step={1} min={0} unit="mm" />
        )}
      </Section>

      <Section title="Colours">
        <ColourOptions />
      </Section>

      <Section title="Text">
        <TextPanel />
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
        <p className="muted hint">{(onShape ? SHAPE_STACKING_HINTS : STACKING_HINTS)[s.stacking]}</p>
        {s.stacking === "full" && !onShape && (
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
            {!onShape && (
              <NumberField label="Base" value={s.base} onChange={(base) => set({ base })} step={0.1} min={0.01} unit="mm" />
            )}
            <NumberField label={s.stacking === "layers" ? "Each colour's layer" : onShape ? "Design depth" : "Coloured top"}
              value={s.layer} onChange={(layer) => set({ layer })} step={0.1} min={0.01} unit="mm" />
          </>
        )}
        {!onShape && (
          <NumberField label="Corner radius" value={s.corner_radius}
            onChange={(corner_radius) => set({ corner_radius })} step={1} min={0} unit="mm" />
        )}
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

/** A box or cylinder, its size, and the face the design goes on. */
function ShapeOptions() {
  const s = useStore((st) => st.settings);
  const set = useStore((st) => st.setSettings);
  const cylinder = s.shape === "cylinder";
  const faces = cylinder ? FACES.slice(0, 2) : FACES;   // a cylinder's side is curved

  return (
    <>
      <Segmented
        label="Base shape"
        value={s.shape}
        options={[
          { value: "box", label: "Box" },
          { value: "cylinder", label: "Cylinder" },
        ]}
        onChange={(shape) => set(shape === "cylinder" && !FACES.slice(0, 2).includes(s.face)
          ? { shape, face: "top" } : { shape })}
      />
      <NumberField label={cylinder ? "Diameter" : "Width"} value={s.shape_width}
        onChange={(shape_width) => set({ shape_width })} step={1} min={1} unit="mm" />
      {!cylinder && (
        <NumberField label="Depth" value={s.shape_depth}
          onChange={(shape_depth) => set({ shape_depth })} step={1} min={1} unit="mm" />
      )}
      <NumberField label="Height" value={s.shape_height}
        onChange={(shape_height) => set({ shape_height })} step={1} min={1} unit="mm" />
      <label className="field">
        <span className="field-label">Design on the</span>
        <select value={s.face} onChange={(e) => set({ face: e.target.value })}>
          {faces.map((f) => <option key={f} value={f}>{f} face</option>)}
        </select>
      </label>
    </>
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
