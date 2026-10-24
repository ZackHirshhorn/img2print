import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { Dropzone } from "./components/Dropzone";
import { Footer } from "./components/Footer";
import { Preview3D } from "./components/Preview3D";
import { Results } from "./components/Results";
import { SettingsPanel } from "./components/SettingsPanel";
import { useStore } from "./store";

const AUTO_BUILD_DELAY = 600;   // ms after the last change

export function App() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info, staleTime: Infinity });
  const { upload, settings, material, autoBuild, model, setModel } = useStore();
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [builtFor, setBuiltFor] = useState<string | null>(null);
  const latest = useRef(0);

  const key = upload ? JSON.stringify([upload.id, settings, material]) : null;
  const stale = key !== null && key !== builtFor;

  const build = useCallback(async () => {
    if (!upload) return;
    const request = ++latest.current;
    const forKey = JSON.stringify([upload.id, settings, material]);
    setBuilding(true);
    setError(null);
    try {
      const built = await api.build(upload.id, settings, material);
      if (request !== latest.current) return;   // a newer build was started meanwhile
      setModel(built);
      setBuiltFor(forKey);
    } catch (e) {
      if (request === latest.current) setError((e as Error).message);
    } finally {
      if (request === latest.current) setBuilding(false);
    }
  }, [upload, settings, material, setModel]);

  // Auto-build once changes settle. `key` covers everything `build` reads.
  useEffect(() => {
    if (!autoBuild || !stale) return;
    const t = setTimeout(build, AUTO_BUILD_DELAY);
    return () => clearTimeout(t);
  }, [key, autoBuild]);

  // The filament figures depend on the material, so a new material re-prices the current build.
  useEffect(() => {
    if (model && !autoBuild) build();
  }, [material]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>img2print</h1>
        <span className="muted">Logos to multi-colour 3D prints</span>
        {info.isError && <span className="error">Server not reachable: {info.error.message}</span>}
      </header>
      <main className="panes">
        <aside className="pane left">
          <Dropzone />
          <SettingsPanel />
        </aside>
        <section className="pane centre" aria-label="Preview">
          <Preview3D model={model} />
          {building && <div className="busy">Building…</div>}
        </section>
        <aside className="pane right">
          <Results info={info.data} model={model} building={building} error={error} stale={stale} onBuild={build} />
        </aside>
      </main>
      <Footer version={info.data?.version} />
    </div>
  );
}
