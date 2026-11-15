"use client";

import { useState } from "react";

export function DocumentPreview({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);

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

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      className="max-h-[80vh] w-full bg-slate-100 object-contain"
      onError={() => setFailed(true)}
    />
  );
}
