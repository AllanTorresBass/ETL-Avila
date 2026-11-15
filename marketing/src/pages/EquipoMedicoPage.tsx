import { useMemo, useState } from "react";
import { DOCTOR_CATEGORIES, DOCTORS } from "../data/content";
import { useAppointment } from "../context/AppointmentContext";

export function EquipoMedicoPage() {
  const { openModal } = useAppointment();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<(typeof DOCTOR_CATEGORIES)[number]>("Todas");

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return DOCTORS.filter((d) => {
      const catOk = category === "Todas" || d.category === category;
      const textOk =
        !query || d.name.toLowerCase().includes(query) || d.specialty.toLowerCase().includes(query);
      return catOk && textOk;
    });
  }, [q, category]);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 pt-28 pb-16 sm:px-6">
      <div>
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">Equipo médico</p>
        <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-5xl">
          Especialistas en cada área de la salud
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Directorio en vivo: {DOCTORS.length} médicos. La cifra publicada en Nosotros es 45+.
        </p>
      </div>

      <input
        className="input-avila max-w-xl"
        placeholder="Buscar por nombre o especialidad médica..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        aria-label="Buscar médicos"
      />

      <div className="flex flex-wrap gap-1 rounded-full bg-slate-100 p-1">
        {DOCTOR_CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCategory(c)}
            className={`rounded-full px-3 py-1.5 text-xs ${
              category === c
                ? "bg-[#033CA0] font-medium text-white shadow-md"
                : "font-medium text-slate-600"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
          <p className="font-medium">No se encontraron médicos</p>
          <p className="mt-1 text-sm text-slate-500">
            Intenta cambiar los términos de búsqueda o el filtro de especialidad.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((d) => (
            <article
              key={d.id}
              className="rounded-3xl border border-slate-100 bg-white p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
            >
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#033CA0]/10 text-sm font-medium text-[#033CA0]">
                {d.name
                  .split(" ")
                  .slice(0, 2)
                  .map((p) => p[0])
                  .join("")}
              </div>
              <h2 className="mt-4 text-sm font-medium">{d.name}</h2>
              <p className="mt-1 text-xs text-slate-500">{d.specialty}</p>
              <button
                type="button"
                onClick={() => openModal({ specialist: d.name })}
                className="btn-green-gradient mt-4 rounded-full px-4 py-2 text-xs font-medium text-white"
              >
                Agendar Cita
              </button>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
