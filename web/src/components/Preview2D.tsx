// The design seen from above, on its plate or face, with the texts on it. Drag a text to move it;
// scroll to zoom and drag the background to pan.
import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { Settings, TextItem } from "../api/client";
import { useStore } from "../store";
import { useTrace } from "../useTrace";

const MARGIN = 0.06;   // of the plate's larger side, around it
const ZOOM_STEP = 1.4;
const MAX_ZOOM = 25;

/** A viewBox: x, y, width, height in mm. */
type Box = [number, number, number, number];

interface Drag {
  index: number;
  start: [number, number];
  offset: [number, number];
}

export function Preview2D() {
  const upload = useStore((s) => s.upload);
  const settings = useStore((s) => s.settings);
  const selected = useStore((s) => s.selectedText);
  const selectText = useStore((s) => s.selectText);
  const setText = useStore((s) => s.setText);
  const addText = useStore((s) => s.addText);
  const traced = useTrace();
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  // The zoomed view, for the plate size it was made for; a new size starts from the whole plate.
  const [zoomed, setZoomed] = useState<{ key: string; box: Box } | null>(null);
  const pan = useRef<{ start: [number, number]; box: Box; moved: boolean } | null>(null);
  const view = useRef<{ box: Box; fit: Box; key: string } | null>(null);

  function zoomAt(at: [number, number], factor: number) {
    const v = view.current;
    if (!v) return;
    const [x, y, bw, bh] = v.box;
    const f = Math.min(Math.max(factor, v.fit[2] / MAX_ZOOM / bw), (2 * v.fit[2]) / bw);
    setZoomed({ key: v.key, box: [at[0] - (at[0] - x) * f, at[1] - (at[1] - y) * f, bw * f, bh * f] });
  }

  const ready = traced.data !== undefined;
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    function onWheel(e: WheelEvent) {   // a native listener: React's wheel events cannot stop the page scrolling
      e.preventDefault();
      zoomAt(clientToView(el!, e.clientX, e.clientY), Math.exp(e.deltaY * 0.0015));
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [ready, upload]);

  if (!upload) {
    return <div className="preview-empty muted">Add a file, or start a blank plate, to see the design.</div>;
  }
  if (!traced.data) {
    return (
      <div className="preview-empty muted">
        {traced.isError ? <span className="error">{traced.error.message}</span> : "Tracing…"}
      </div>
    );
  }
  const { trace, settings: tracedFor } = traced.data;
  const { width: w, height: h } = trace;
  const plate = plateOf(settings, w, h);
  const pad = MARGIN * Math.max(plate.width, plate.height);
  const fit: Box = [-pad, -pad, plate.width + 2 * pad, plate.height + 2 * pad];
  const key = fit.join(" ");
  const box = zoomed?.key === key ? zoomed.box : fit;
  view.current = { box, fit, key };

  /** A pointer position in design millimetres (y down). */
  function toMm(e: PointerEvent): [number, number] {
    const [x, y] = clientToView(svg.current!, e.clientX, e.clientY);
    return [x - plate.dx, y - plate.dy];
  }

  function startDrag(index: number, e: PointerEvent) {
    e.stopPropagation();
    selectText(index);
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    setDrag({ index, start: toMm(e), offset: [0, 0] });
  }

  function startPan(e: PointerEvent) {
    e.currentTarget.setPointerCapture(e.pointerId);
    pan.current = { start: [e.clientX, e.clientY], box, moved: false };
  }

  function moveDrag(e: PointerEvent) {
    const p = pan.current;
    if (p) {
      const mmPerPx = 1 / svg.current!.getScreenCTM()!.a;
      const dx = (e.clientX - p.start[0]) * mmPerPx;
      const dy = (e.clientY - p.start[1]) * mmPerPx;
      if (Math.abs(e.clientX - p.start[0]) + Math.abs(e.clientY - p.start[1]) > 3) p.moved = true;
      if (p.moved) setZoomed({ key, box: [p.box[0] - dx, p.box[1] - dy, p.box[2], p.box[3]] });
      return;
    }
    if (!drag) return;
    const [x, y] = toMm(e);
    setDrag({ ...drag, offset: [x - drag.start[0], y - drag.start[1]] });
  }

  function endDrag() {
    if (pan.current) {
      if (!pan.current.moved) selectText(null);   // a click on the background
      pan.current = null;
      return;
    }
    if (!drag) return;
    const [dx, dy] = drag.offset;
    const t = settings.texts[drag.index];
    if (t && (dx || dy)) setText(drag.index, { x: round(t.x + dx / w), y: round(t.y + dy / h) });
    setDrag(null);
  }

  return (
    <div className="preview2d">
      <svg
        ref={svg}
        viewBox={box.join(" ")}
        preserveAspectRatio="xMidYMid meet"
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={() => { setDrag(null); pan.current = null; }}
        onPointerDown={startPan}
        onDoubleClick={(e) => {
          if ((e.target as Element).closest(".text-shape")) return;
          const [x, y] = toMm(e as unknown as PointerEvent);
          addText({ x: round(x / w), y: round(y / h), text: "טקסט" });
        }}
        className={pan.current?.moved ? "panning" : ""}
        aria-label="Design preview: drag a text to move it, double-click to add one, scroll to zoom"
      >
        <defs>
          <clipPath id="plate-clip">{plate.outline}</clipPath>
        </defs>
        <g className="plate" fill={trace.layers[0]?.color}>{plate.outline}</g>
        <g clipPath="url(#plate-clip)">
          <g transform={`translate(${plate.dx} ${plate.dy})`}>
            {trace.layers.map((l) => (
              <path key={l.name} d={l.path} fill={l.color} fillRule="evenodd" />
            ))}
          </g>
        </g>
        <g transform={`translate(${plate.dx} ${plate.dy})`}>
          {settings.texts.map((t, i) => {
            const shape = trace.texts?.[i];
            const was = tracedFor.texts[i];
            if (!shape?.path || !was) return null;
            const off = drag?.index === i ? drag.offset : [0, 0];
            return (
              <path
                key={i}
                d={shape.path}
                fillRule="evenodd"
                className={`text-shape ${t.style}${selected === i ? " selected" : ""}`}
                fill={t.color ?? "none"}
                transform={moved(t, was, w, h, off)}
                onPointerDown={(e) => startDrag(i, e)}
              />
            );
          })}
        </g>
        <g className="plate-edge">{plate.outline}</g>
      </svg>
      <div className="zoom-buttons">
        <button type="button" aria-label="Zoom in" onClick={() => zoomAt(centre(box), 1 / ZOOM_STEP)}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomAt(centre(box), ZOOM_STEP)}>−</button>
        <button type="button" onClick={() => setZoomed(null)} disabled={box === fit}>Fit</button>
      </div>
      <p className="preview-hint muted small">
        {w.toFixed(1)} × {h.toFixed(1)} mm design. Drag a text to move it; double-click to add one.
        Scroll to zoom, drag the background to pan.
      </p>
    </div>
  );
}

/** Where the server drew a text, to where it is now: the move and turn made since (or being dragged). */
function moved(now: TextItem, was: TextItem, w: number, h: number, drag: number[]): string {
  const cx = was.x * w;
  const cy = was.y * h;
  const dx = (now.x - was.x) * w + drag[0];
  const dy = (now.y - was.y) * h + drag[1];
  const turn = -(now.rotation - was.rotation);   // counter-clockwise with y up is clockwise on screen
  return `translate(${dx} ${dy}) rotate(${turn} ${cx} ${cy})`;
}

const round = (v: number) => Math.round(v * 10000) / 10000;
const centre = (b: Box): [number, number] => [b[0] + b[2] / 2, b[1] + b[3] / 2];

/** A screen position in the SVG's viewBox units. */
function clientToView(el: SVGSVGElement, x: number, y: number): [number, number] {
  const pt = el.createSVGPoint();
  pt.x = x;
  pt.y = y;
  const p = pt.matrixTransform(el.getScreenCTM()!.inverse());
  return [p.x, p.y];
}

/** The plate (or the shape's face) around a w × h mm design, and where the design sits on it. */
function plateOf(s: Settings, w: number, h: number) {
  if (s.recipe === "shape") {
    const cylinder = s.shape === "cylinder";
    const [fw, fh] = cylinder ? [s.shape_width, s.shape_width]
      : s.face === "top" || s.face === "bottom" ? [s.shape_width, s.shape_depth]
        : s.face === "front" || s.face === "back" ? [s.shape_width, s.shape_height]
          : [s.shape_depth, s.shape_height];
    const outline = cylinder
      ? <circle cx={fw / 2} cy={fh / 2} r={fw / 2} />
      : <rect width={fw} height={fh} />;
    return { width: fw, height: fh, dx: (fw - w) / 2, dy: (fh - h) / 2, outline };
  }
  const pw = w + 2 * s.padding;
  const ph = h + 2 * s.padding;
  const r = Math.min(s.corner_radius, pw / 2, ph / 2);
  return { width: pw, height: ph, dx: s.padding, dy: s.padding, outline: <rect width={pw} height={ph} rx={r} /> };
}
