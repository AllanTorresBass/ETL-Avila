"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const MIN_SCALE = 1;
const MAX_SCALE = 4;
const STEP = 0.25;

function clampScale(value: number) {
  const stepped = Math.round(value / STEP) * STEP;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Number(stepped.toFixed(2))));
}

function clampOffset(
  x: number,
  y: number,
  scale: number,
  frame: DOMRect | undefined,
) {
  if (!frame || scale <= MIN_SCALE) return { x: 0, y: 0 };
  const maxX = (frame.width * (scale - 1)) / 2;
  const maxY = (frame.height * (scale - 1)) / 2;
  return {
    x: Math.min(maxX, Math.max(-maxX, x)),
    y: Math.min(maxY, Math.max(-maxY, y)),
  };
}

export function DocumentPreview({ src, alt }: { src: string; alt: string }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);
  const scaleRef = useRef(1);
  const offsetRef = useRef({ x: 0, y: 0 });
  const [failed, setFailed] = useState(false);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  const applyZoom = useCallback((nextRaw: number, origin?: { x: number; y: number }) => {
    const next = clampScale(nextRaw);
    const current = scaleRef.current;
    const currentOffset = offsetRef.current;
    if (next === current) return;
    const frame = frameRef.current?.getBoundingClientRect();
    let nextOffset = { x: 0, y: 0 };
    if (next > MIN_SCALE) {
      if (origin && frame) {
        const px = origin.x - frame.left - frame.width / 2;
        const py = origin.y - frame.top - frame.height / 2;
        nextOffset = {
          x: currentOffset.x + px * (current - next),
          y: currentOffset.y + py * (current - next),
        };
      } else {
        nextOffset = {
          x: currentOffset.x * (next / current),
          y: currentOffset.y * (next / current),
        };
      }
      nextOffset = clampOffset(nextOffset.x, nextOffset.y, next, frame);
    }
    scaleRef.current = next;
    offsetRef.current = nextOffset;
    setScale(next);
    setOffset(nextOffset);
  }, []);

  useEffect(() => {
    scaleRef.current = 1;
    offsetRef.current = { x: 0, y: 0 };
    setFailed(false);
    setScale(1);
    setOffset({ x: 0, y: 0 });
  }, [src]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || failed) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const direction = event.deltaY < 0 ? STEP : -STEP;
      applyZoom(scaleRef.current + direction, { x: event.clientX, y: event.clientY });
    };
    frame.addEventListener("wheel", onWheel, { passive: false });
    return () => frame.removeEventListener("wheel", onWheel);
  }, [applyZoom, failed]);

  if (failed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 bg-slate-100 px-6 text-center text-sm text-slate-500">
        <p>No se pudo cargar la imagen</p>
        <p className="text-xs">El documento puede haber fallado en Blob o el enlace expiró.</p>
        <a href={src} className="text-xs text-[#033CA0] underline" target="_blank" rel="noopener noreferrer">
          Abrir ruta de API
        </a>
      </div>
    );
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (scaleRef.current <= MIN_SCALE || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      px: event.clientX,
      py: event.clientY,
      ox: offsetRef.current.x,
      oy: offsetRef.current.y,
    };
    setDragging(true);
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    const frame = frameRef.current?.getBoundingClientRect();
    const next = clampOffset(
      drag.ox + event.clientX - drag.px,
      drag.oy + event.clientY - drag.py,
      scaleRef.current,
      frame,
    );
    offsetRef.current = next;
    setOffset(next);
  }

  function onPointerUp() {
    dragRef.current = null;
    setDragging(false);
  }

  function onDoubleClick(event: React.MouseEvent<HTMLDivElement>) {
    if (scaleRef.current > MIN_SCALE) applyZoom(MIN_SCALE);
    else applyZoom(2, { x: event.clientX, y: event.clientY });
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      applyZoom(scaleRef.current + STEP);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      applyZoom(scaleRef.current - STEP);
    } else if (event.key === "0") {
      event.preventDefault();
      applyZoom(MIN_SCALE);
    }
  }

  const percent = Math.round(scale * 100);

  return (
    <div className="relative bg-slate-100">
      <div
        ref={frameRef}
        role="region"
        tabIndex={0}
        aria-label={`Vista del documento, ${percent}%`}
        className="max-h-[80vh] overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-[#033CA0]"
        style={{
          cursor: scale > MIN_SCALE ? (dragging ? "grabbing" : "grab") : "zoom-in",
          touchAction: scale > MIN_SCALE ? "none" : "pan-y",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={onDoubleClick}
        onKeyDown={onKeyDown}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          draggable={false}
          className="max-h-[80vh] w-full bg-slate-100 object-contain select-none"
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            transformOrigin: "center center",
          }}
          onError={() => setFailed(true)}
        />
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
        <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-white/80 bg-white/90 px-1.5 py-1 shadow-sm backdrop-blur">
          <button
            type="button"
            aria-label="Alejar"
            disabled={scale <= MIN_SCALE}
            onClick={() => applyZoom(scale - STEP)}
            className="rounded-full px-3 py-1.5 text-sm font-medium text-[#0A2A6B] hover:bg-slate-100 disabled:opacity-40"
          >
            −
          </button>
          <span className="min-w-12 text-center text-xs font-medium text-[#0A2A6B]">{percent}%</span>
          <button
            type="button"
            aria-label="Acercar"
            disabled={scale >= MAX_SCALE}
            onClick={() => applyZoom(scale + STEP)}
            className="rounded-full px-3 py-1.5 text-sm font-medium text-[#0A2A6B] hover:bg-slate-100 disabled:opacity-40"
          >
            +
          </button>
          <button
            type="button"
            aria-label="Ajustar"
            disabled={scale === MIN_SCALE}
            onClick={() => applyZoom(MIN_SCALE)}
            className="rounded-full px-3 py-1.5 text-xs font-medium text-[#033CA0] hover:bg-slate-100 disabled:opacity-40"
          >
            Ajustar
          </button>
        </div>
      </div>
    </div>
  );
}
