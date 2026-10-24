// What the build produced: size, filament per part, downloads.
import type { BuiltModel, Info } from "../api/client";
import { useStore } from "../store";

const fmt = (v: number, digits = 1) => v.toLocaleString(undefined, { maximumFractionDigits: digits });

export function Results({ info, model, building, error, stale, onBuild }: {
  info: Info | undefined;
  model: BuiltModel | null;
  building: boolean;
  error: string | null;
  stale: boolean;
  onBuild: () => void;
}) {
  const upload = useStore((s) => s.upload);
  const material = useStore((s) => s.material);
  const setMaterial = useStore((s) => s.setMaterial);
  const autoBuild = useStore((s) => s.autoBuild);
  const setAutoBuild = useStore((s) => s.setAutoBuild);

  const totals = model?.parts.reduce(
    (t, p) => ({ grams: t.grams + p.grams, metres: t.metres + p.metres, volume: t.volume + p.volume }),
    { grams: 0, metres: 0, volume: 0 },
  );
  const leaky = model?.parts.filter((p) => !p.watertight) ?? [];

  return (
    <div className="results">
      <div className="build-bar">
        <button type="button" className="primary" disabled={!upload || building} onClick={onBuild}>
          {building ? "Building…" : model && !stale ? "Rebuild" : "Build model"}
        </button>
        <label className="toggle">
          <input type="checkbox" checked={autoBuild} onChange={(e) => setAutoBuild(e.target.checked)} />
          <span>Auto</span>
        </label>
      </div>
      {!upload && <p className="muted">Add a file to start.</p>}
      {error && <p className="error">{error}</p>}
      {model && stale && !building && <p className="muted">Settings changed since this build.</p>}

      {model && totals && (
        <>
          <p className="size">
            {fmt(model.size[0])} × {fmt(model.size[1])} × {fmt(model.size[2], 2)} mm
          </p>

          <label className="field">
            <span className="field-label">Material</span>
            <select value={material} onChange={(e) => setMaterial(e.target.value)}>
              {(info?.materials ?? [material]).map((m) => <option key={m}>{m}</option>)}
            </select>
          </label>

          <table className="parts">
            <thead>
              <tr><th>Part</th><th>cm³</th><th>g</th><th>m</th><th /></tr>
            </thead>
            <tbody>
              {model.parts.map((p) => (
                <tr key={p.name}>
                  <td>
                    <span className="chip" style={{ background: p.color ?? "#888" }} />
                    <span dir="auto">{p.name}</span>
                    {!p.watertight && <span className="warn" title="This part is not watertight">!</span>}
                  </td>
                  <td>{fmt(p.volume / 1000, 2)}</td>
                  <td>{fmt(p.grams)}</td>
                  <td>{fmt(p.metres, 2)}</td>
                  <td><a href={p.stl_url} download title={`Download ${p.name} as STL`}>STL</a></td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Total</td>
                <td>{fmt(totals.volume / 1000, 2)}</td>
                <td>{fmt(totals.grams)}</td>
                <td>{fmt(totals.metres, 2)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
          <p className="muted small">Solid {model.material}; infill makes real prints lighter.</p>
          {leaky.length > 0 && (
            <p className="error">
              Not watertight: {leaky.map((p) => p.name).join(", ")}. The slicer may repair it, but check the print.
            </p>
          )}

          {model.filament_changes.length > 0 && (
            <div className="filament-changes">
              <p className="field-label">Colour by layer: start with {model.parts[0].name}, then pause and load</p>
              <ul>
                {model.filament_changes.map((c) => (
                  <li key={c.name}>
                    <span className="chip" style={{ background: c.color ?? "#888" }} />
                    <span dir="auto">{c.name}</span> at {fmt(c.height, 2)} mm
                  </li>
                ))}
              </ul>
              <p className="muted small">
                In the slicer, add a filament change (pause / M600) at the first layer that starts at each height.
              </p>
            </div>
          )}

          <div className="downloads">
            <a className="button primary" href={model.threemf_url} download>Download 3MF</a>
            <a className="button" href={model.zip_url} download>All files (ZIP)</a>
          </div>
          <p className="muted small">
            Open the 3MF in Bambu Studio, Orca or PrusaSlicer: one object, one part per colour.
          </p>
        </>
      )}
    </div>
  );
}
