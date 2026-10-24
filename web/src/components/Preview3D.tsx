// The built model in 3D: one coloured mesh per part on a build plate grid.
import { Suspense, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { BuiltModel } from "../api/client";
import { useStore } from "../store";

export function Preview3D({ model }: { model: BuiltModel | null }) {
  const hidden = useStore((s) => s.hidden);
  const togglePart = useStore((s) => s.togglePart);
  const explode = useStore((s) => s.explode);
  const setExplode = useStore((s) => s.setExplode);

  if (!model) {
    return <div className="preview-empty muted">Build the model to see it in 3D.</div>;
  }
  const span = Math.max(...model.size, 20);

  return (
    <div className="preview3d">
      <Canvas camera={{ position: [0, span * 0.9, span * 0.9], fov: 40, near: 0.5, far: span * 20 }} dpr={[1, 2]}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[span, span * 2, span]} intensity={1.6} />
        <directionalLight position={[-span, span, -span]} intensity={0.5} />
        <Suspense fallback={null}>
          <Parts url={model.glb_url} model={model} hidden={hidden} explode={explode} />
        </Suspense>
        <Grid
          args={[span * 2, span * 2]}
          cellSize={5}
          sectionSize={50}
          cellColor="#8a8f98"
          sectionColor="#5b616b"
          fadeDistance={span * 4}
          infiniteGrid
        />
        <OrbitControls makeDefault target={[0, 0, 0]} maxPolarAngle={Math.PI * 0.95} />
      </Canvas>

      <div className="preview-controls">
        <div className="part-toggles">
          {model.parts.map((p) => (
            <label key={p.name} className="toggle">
              <input type="checkbox" checked={!hidden.includes(p.name)} onChange={() => togglePart(p.name)} />
              <span className="chip" style={{ background: p.color ?? "#888" }} />
              <span dir="auto">{p.name}</span>
            </label>
          ))}
        </div>
        <label className="field inline">
          <span className="field-label">Explode</span>
          <input type="range" min={0} max={10} step={0.5} value={explode}
            onChange={(e) => setExplode(Number(e.target.value))} />
        </label>
      </div>
    </div>
  );
}

function Parts({ url, model, hidden, explode }: {
  url: string;
  model: BuiltModel;
  hidden: string[];
  explode: number;
}) {
  const gltf = useLoader(GLTFLoader, url);

  // Each part's node, its index in the part list (for exploding) and a material in its colour.
  const parts = useMemo(() => {
    const root = gltf.scene.clone(true);
    const byName = new Map(model.parts.map((p, i) => [THREE.PropertyBinding.sanitizeNodeName(p.name), i]));
    const found: { node: THREE.Object3D; index: number; name: string; z: number }[] = [];
    root.traverse((o) => {
      const index = byName.get(o.name);
      if (index === undefined || found.some((f) => f.index === index)) return;
      const part = model.parts[index];
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(part.color ?? "#888888"),
        roughness: 0.55,
        metalness: 0,
      });
      o.traverse((m) => {
        if ((m as THREE.Mesh).isMesh) (m as THREE.Mesh).material = material;
      });
      found.push({ node: o, index, name: part.name, z: o.position.z });
    });
    // Centre on the plate: trimesh is Z-up, so x/y are the footprint.
    const box = new THREE.Box3().setFromObject(root);
    const centre = box.getCenter(new THREE.Vector3());
    const offset: [number, number, number] = [-centre.x, -centre.y, -box.min.z];
    return { root, found, offset };
  }, [gltf, model]);

  for (const f of parts.found) {
    f.node.visible = !hidden.includes(f.name);
    f.node.position.z = f.z + f.index * explode;
  }

  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <group position={parts.offset}>
        <primitive object={parts.root} />
      </group>
    </group>
  );
}
