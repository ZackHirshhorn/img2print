// Small form controls shared by the panels.
import { useEffect, useId, useState, type ReactNode } from "react";

interface NumberFieldProps {
  label: ReactNode;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  unit?: string;
  integer?: boolean;
}

/** A number input that only reports valid numbers, but lets you type freely in between. */
export function NumberField({ label, value, onChange, step = 0.1, min, max, unit, integer }: NumberFieldProps) {
  const id = useId();
  const [text, setText] = useState(String(value));
  useEffect(() => {
    if (Number(text) !== value) setText(String(value));
  }, [value]);   // follow outside changes only, not our own typing

  function commit(raw: string) {
    setText(raw);
    const v = Number(raw);
    if (raw.trim() === "" || !Number.isFinite(v)) return;
    if ((min != null && v < min) || (max != null && v > max) || (integer && !Number.isInteger(v))) return;
    onChange(v);
  }

  return (
    <label className="field" htmlFor={id}>
      <span className="field-label">{label}</span>
      <span className="field-input">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          value={text}
          step={step}
          min={min}
          max={max}
          onChange={(e) => commit(e.target.value)}
          onBlur={() => setText(String(value))}
        />
        {unit && <span className="unit">{unit}</span>}
      </span>
    </label>
  );
}

export function Toggle({ label, checked, onChange, hint }: {
  label: ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="toggle" title={hint}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? "on" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
