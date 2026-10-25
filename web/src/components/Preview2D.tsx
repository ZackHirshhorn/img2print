// The design seen from above, on its plate or face, with the texts on it. Drag a text to move it.
import { useRef, useState, type PointerEvent } from "react";
import type { Settings, TextItem } from "../api/client";
import { useStore } from "../store";
import { useTrace } from "../useTrace";

const MARGIN = 0.06;   // of the plate's larger side, around it

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

  /** A pointer position in design millimetres (y down). */
  function toMm(e: PointerEvent): [number, number] {
    const el = svg.current!;
    const pt = el.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(el.getScreenCTM()!.inverse());
    return [p.x - plate.dx, p.y - plate.dy];
  }

  function startDrag(index: number, e: PointerEvent) {
    e.stopPropagation();
    selectText(index);
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    setDrag({ index, start: toMm(e), offset: [0, 0] });
  }

  function moveDrag(e: PointerEvent) {
    if (!drag) return;
    const [x, y] = toMm(e);
    setDrag({ ...drag, offset: [x - drag.start[0], y - drag.start[1]] });
  }

  function endDrag() {
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
        viewBox={`${-pad} ${-pad} ${plate.width + 2 * pad} ${plate.height + 2 * pad}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={() => setDrag(null)}
        onPointerDown={() => selectText(null)}
        onDoubleClick={(e) => {
          if ((e.target as Element).closest(".text-shape")) return;
          const [x, y] = toMm(e as unknown as PointerEvent);
          addText({ x: round(x / w), y: round(y / h), text: "טקסט" });
        }}
        aria-label="Design preview: drag a text to move it, double-click to add one"
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
      <p className="preview-hint muted small">
        {w.toFixed(1)} × {h.toFixed(1)} mm design. Drag a text to move it; double-click to add one.
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
