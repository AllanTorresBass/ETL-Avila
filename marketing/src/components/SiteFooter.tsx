import { Link } from "react-router-dom";
import { CONTACT_INFO, NAV_LINKS, WA_URL } from "../data/content";

export function SiteFooter() {
  return (
    <footer className="mt-16 bg-[#0A1F4D] px-4 py-12 text-white sm:px-6">
      <div className="mx-auto grid max-w-6xl gap-8 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <p className="text-sm font-semibold">Ávila GPS</p>
          <p className="mt-2 text-xs font-light text-white/75">
            Gestión Profesional de Salud. Atención integral en Valera y todo el país.
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[#5BB2F5]">Navegación</p>
          <ul className="mt-3 space-y-2 text-sm">
            {NAV_LINKS.map((l) => (
              <li key={l.to}>
                <Link to={l.to} className="text-white/80 hover:text-white">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[#5BB2F5]">Contacto Directo</p>
          <ul className="mt-3 space-y-2 text-sm text-white/80">
            <li>{CONTACT_INFO.phones}</li>
            <li>
              <a href={`mailto:${CONTACT_INFO.email}`} className="hover:text-white">
                {CONTACT_INFO.email}
              </a>
            </li>
            <li>
              <a href={WA_URL} target="_blank" rel="noopener noreferrer" className="hover:text-white">
                WhatsApp
              </a>
            </li>
            <li>{CONTACT_INFO.instagram}</li>
          </ul>
        </div>
      </div>
      <p className="mx-auto mt-10 max-w-6xl text-center text-[11px] text-white/55">
        © 2025 Ávila Gestión Profesional de Salud. Todos los derechos reservados. | Hecho por Legaint
        Corporation
      </p>
    </footer>
  );
}
