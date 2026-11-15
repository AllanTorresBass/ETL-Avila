import { Link } from "react-router-dom";
import { PartnerCarousel } from "../components/PartnerCarousel";
import { useAppointment } from "../context/AppointmentContext";
import { HERO_CHIPS, HOME_GRID, HOME_UNITS, PROOF } from "../data/content";

export function HomePage() {
  const { openModal } = useAppointment();

  return (
    <div>
      <section className="relative flex min-h-[92vh] flex-col justify-center bg-[#0A2A6B] px-4 pt-28 pb-16 text-white sm:px-6 lg:min-h-screen">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_#033CA055,_transparent_55%)]" />
        <div className="relative mx-auto max-w-6xl">
          <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">Ávila GPS</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-medium tracking-tight [text-shadow:0_2px_16px_rgba(0,0,0,0.25)] sm:text-6xl lg:text-7xl">
            Atención médica integral, cuando la necesitas.
          </h1>
          <p className="mt-4 max-w-xl text-sm font-light text-white/85 sm:text-base">
            Médicos en el hogar, telemedicina 12 h/7 y red de especialidades en Valera, Trujillo.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => openModal()}
              className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
            >
              Solicitar atención
            </button>
            <Link
              to="/nosotros"
              className="rounded-full border border-white/40 bg-[#033CA0]/55 px-5 py-2.5 text-xs font-medium text-white backdrop-blur"
            >
              Conoce más
            </Link>
          </div>
          <div className="mt-10 flex flex-wrap gap-2">
            {HERO_CHIPS.map((chip) => (
              <span
                key={chip}
                className="rounded-2xl border border-white/25 bg-white/10 px-3 py-2 text-xs backdrop-blur"
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-16 px-4 py-16 sm:px-6">
        <section>
          <h2 className="text-3xl font-medium tracking-tight sm:text-4xl">Unidades Médicas Especializadas</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {HOME_UNITS.map((unit) => (
              <button
                key={unit.id}
                type="button"
                onClick={() => openModal({ service: unit.title.includes("Cardiología") ? "Consultas con especialistas" : unit.title })}
                className="group rounded-3xl border border-white bg-white/90 p-6 text-left shadow-sm backdrop-blur-md transition hover:-translate-y-1.5 hover:shadow-2xl"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-100 bg-slate-50 group-hover:bg-[#6CC24A]">
                  <span className="text-lg font-medium text-[#033CA0] group-hover:text-white">+</span>
                </div>
                <h3 className="mt-4 text-sm font-medium">{unit.title}</h3>
                <p className="mt-2 text-xs font-light text-slate-600">{unit.summary}</p>
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-3xl font-medium tracking-tight sm:text-4xl">¿Qué ofrecemos?</h2>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {HOME_GRID.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => openModal({ service: item.includes("Telemedicina") ? "Telemedicina" : "Consultas con especialistas" })}
                className="rounded-3xl border border-slate-100 bg-white p-5 text-left text-sm shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-3xl font-medium tracking-tight sm:text-4xl">¿Por qué elegirnos?</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PROOF.map((p) => (
              <div key={p.title} className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
                <p className="text-sm font-medium">{p.title}</p>
                <p className="mt-1 text-xs text-slate-500">{p.subtitle}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-3xl bg-gradient-to-r from-[#033CA0] via-[#0A2A6B] to-[#0F7A33] px-6 py-10 text-white sm:px-10">
          <p className="max-w-2xl text-lg font-light sm:text-xl">
            Cuidamos a tu familia con la misma dedicación con la que gestionamos cada caso clínico.
          </p>
          <button
            type="button"
            onClick={() => openModal()}
            className="btn-green-gradient mt-6 rounded-full px-5 py-2.5 text-xs font-medium text-white"
          >
            Solicitar atención
          </button>
        </section>

        <PartnerCarousel />

        <section className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
          <h2 className="text-2xl font-medium tracking-tight">Atención humana, procesos claros</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500">
            Conoce nuestro equipo y la historia detrás de Ávila GPS.
          </p>
          <Link
            to="/nosotros"
            className="btn-green-gradient mt-6 inline-flex rounded-full px-5 py-2.5 text-xs font-medium text-white"
          >
            Ir a Nosotros
          </Link>
        </section>
      </div>
    </div>
  );
}
