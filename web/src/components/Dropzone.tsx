// Drop, paste or browse for a PNG / JPG / SVG / PDF; shows what was uploaded.
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useStore } from "../store";

const ACCEPT = "image/*,.svg,.pdf,application/pdf";

export function Dropzone() {
  const upload = useStore((s) => s.upload);
  const previewUrl = useStore((s) => s.previewUrl);
  const page = useStore((s) => s.settings.page);
  const setUpload = useStore((s) => s.setUpload);
  const setSettings = useStore((s) => s.setSettings);
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const send = useMutation({
    mutationFn: (file: File) => api.upload(file).then((u) => ({ u, file })),
    onSuccess: ({ u, file }) => setUpload(u, file),
  });

  const { mutate } = send;
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const file = e.clipboardData?.files[0];
      if (file) mutate(file);
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [mutate]);

  const pick = (files: FileList | null) => files?.[0] && mutate(files[0]);

  return (
    <div className="dropzone-wrap">
      <button
        type="button"
        className={`dropzone${over ? " over" : ""}${upload ? " has-file" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          pick(e.dataTransfer.files);
        }}
      >
        {upload && previewUrl && upload.kind !== "pdf" ? (
          <img className="thumb" src={previewUrl} alt="" />
        ) : upload ? (
          <span className="thumb-pdf">PDF</span>
        ) : null}
        <span className="dropzone-text">
          {send.isPending
            ? "Reading the file…"
            : upload
              ? "Drop another file, paste, or click to replace"
              : "Drop a logo here, paste it, or click to browse"}
          <small>PNG, JPG, SVG or PDF</small>
        </span>
      </button>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => pick(e.target.files)} />

      {send.isError && <p className="error">{send.error.message}</p>}

      {upload && (
        <div className="file-info">
          <span className="file-name" dir="auto" title={upload.filename}>{upload.filename}</span>
          <span className="muted">
            {upload.kind === "raster"
              ? `${upload.width} × ${upload.height} px`
              : `${upload.kind.toUpperCase()}, ${Math.round(upload.width)} × ${Math.round(upload.height)}`}
          </span>
          {upload.pages > 1 && (
            <label className="field">
              <span className="field-label">Page</span>
              <select value={page} onChange={(e) => setSettings({ page: Number(e.target.value) })}>
                {Array.from({ length: upload.pages }, (_, i) => (
                  <option key={i} value={i + 1}>{i + 1} of {upload.pages}</option>
                ))}
              </select>
            </label>
          )}
          {upload.colors.length > 0 && (
            <div className="swatches" aria-label="Main colours in the file">
              {upload.colors.map((c) => (
                <span key={c.color} className="swatch" title={`${c.name} ${c.color}, ${Math.round(c.share * 100)}%`}>
                  <span className="chip" style={{ background: c.color }} />
                  {Math.round(c.share * 100)}%
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
