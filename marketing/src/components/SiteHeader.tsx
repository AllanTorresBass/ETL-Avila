import { Menu, X } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { NAV_LINKS } from "../data/content";
import { useAppointment } from "../context/AppointmentContext";

export function SiteHeader() {
  const { pathname } = useLocation();
  const { openModal } = useAppointment();
  const [drawer, setDrawer] = useState(false);

  return (
    <header className="fixed top-3 right-3 left-3 z-40 sm:top-5 sm:right-5 sm:left-5">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 rounded-full border border-white/70 bg-white/70 px-4 py-2 shadow-sm backdrop-blur-md sm:px-5">
        <Link to="/" className="text-sm font-semibold tracking-tight text-[#0A2A6B]">
          Ávila GPS
        </Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Principal">
          {NAV_LINKS.map((link) => {
            const active = pathname === link.to;
            return (
              <Link
                key={link.to}
                to={link.to}
                aria-current={active ? "page" : undefined}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  active
                    ? "bg-[#033CA0]/10 text-[#033CA0]"
                    : "text-slate-600 hover:bg-[#033CA0]/10 hover:text-[#033CA0]"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => openModal()}
            className="btn-green-gradient hidden rounded-full px-4 py-2 text-xs font-medium text-white sm:inline-flex"
          >
            Solicitar Atención
          </button>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-[#0A2A6B] md:hidden"
            aria-label={drawer ? "Cerrar menú" : "Abrir menú"}
            onClick={() => setDrawer((v) => !v)}
          >
            {drawer ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {drawer ? (
        <div className="mt-2 ml-auto max-w-sm rounded-3xl border border-slate-100 bg-white/95 p-4 shadow-lg backdrop-blur md:hidden">
          <nav className="flex flex-col gap-1" aria-label="Móvil">
            {NAV_LINKS.map((link) => {
              const active = pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setDrawer(false)}
                  className={`rounded-full px-3 py-2 text-sm font-medium ${
                    active ? "bg-[#033CA0]/10 text-[#033CA0]" : "text-slate-600"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={() => {
                setDrawer(false);
                openModal();
              }}
              className="btn-green-gradient mt-2 rounded-full px-4 py-2.5 text-xs font-medium text-white"
            >
              Solicitar Atención
            </button>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
