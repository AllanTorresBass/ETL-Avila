import { Link } from "react-router-dom";
import { useAppointment } from "../context/AppointmentContext";
import { ALLIED_CLINICS, PUBLISHED_STATS } from "../data/content";

export function NosotrosPage() {
  const { openModal } = useAppointment();

  return (
    <div className="mx-auto max-w-6xl space-y-16 px-4 pt-28 pb-16 sm:px-6">
      <section>
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">Nosotros</p>
        <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-5xl">
          Gestión Profesional de Salud en Valera
        </h1>
        <p className="mt-4 max-w-2xl text-sm font-light text-slate-600 sm:text-base">
          Ávila GPS coordina atención médica integral: consultas en el hogar, telemedicina 12 h/7,
          laboratorio y una red de especialistas y clínicas aliadas. Nuestro compromiso es claridad
          operativa y cuidado humano en cada caso.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-medium tracking-tight">Cifras publicadas</h2>
        <p className="mt-1 text-xs text-slate-500">
          Figuras de marketing del sitio. El directorio en vivo lista {48} médicos.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PUBLISHED_STATS.map((s) => (
            <article key={s.label} className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
              <p className="text-3xl font-medium text-[#033CA0]">{s.value}</p>
              <p className="mt-2 text-sm font-medium">{s.label}</p>
              <p className="mt-1 text-xs text-slate-500">{s.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-medium tracking-tight">Clínicas y aliados en Valera</h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ALLIED_CLINICS.map((c) => (
            <article key={c.name} className="rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
              <p className="text-sm font-medium">{c.name}</p>
              <p className="mt-1 text-xs text-slate-500">
                {c.city} · {c.tag}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
        <h2 className="text-xl font-medium">¿Listo para agendar?</h2>
        <div className="mt-4 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={() => openModal()}
            className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
          >
            Solicitar atención
          </button>
          <Link
            to="/equipo-medico"
            className="rounded-full border border-slate-200 px-5 py-2.5 text-xs font-medium text-[#033CA0]"
          >
            Ver equipo médico
          </Link>
        </div>
      </section>
    </div>
  );
}
