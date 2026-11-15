import { PARTNERS, SERVICES } from "../data/content";
import { useAppointment } from "../context/AppointmentContext";

export function ServiciosPage() {
  const { openModal } = useAppointment();
  const aseguradoras = PARTNERS.filter((p) => p.sector.includes("Aseguradora"));
  const empresas = PARTNERS.filter((p) => !p.sector.includes("Aseguradora"));

  return (
    <div className="mx-auto max-w-6xl space-y-16 px-4 pt-28 pb-16 sm:px-6">
      <section>
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">Servicios</p>
        <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-5xl">
          Portafolio Médico Integral & Especializado
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-slate-500">
          Cada servicio puede abrirse en la solicitud de atención con el contexto ya seleccionado.
        </p>
      </section>

      <div className="space-y-10">
        {SERVICES.map((service, index) => (
          <article
            key={service.id}
            className={`flex flex-col gap-6 rounded-3xl border border-slate-100 bg-white p-6 shadow-sm lg:items-center lg:p-8 ${
              index % 2 === 1 ? "lg:flex-row-reverse" : "lg:flex-row"
            }`}
          >
            <div className="flex h-40 flex-1 items-center justify-center rounded-2xl bg-[#033CA0]/10 text-[#033CA0]">
              <span className="text-sm font-medium">{service.title.split(" ")[0]}</span>
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-medium tracking-tight">{service.title}</h2>
              <p className="mt-2 text-sm text-slate-600">{service.summary}</p>
              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-500">
                {service.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() =>
                  openModal({
                    service:
                      service.id === "telemedicine"
                        ? "Telemedicina"
                        : service.id === "home-consultations"
                          ? "Consultas en el hogar"
                          : "Consultas con especialistas",
                  })
                }
                className="btn-green-gradient mt-5 rounded-full px-5 py-2.5 text-xs font-medium text-white"
              >
                Solicitar {service.title}
              </button>
            </div>
          </article>
        ))}
      </div>

      <section className="grid gap-8 lg:grid-cols-2">
        <div>
          <h2 className="text-xl font-medium">Aseguradoras</h2>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {aseguradoras.map((p) => (
              <div key={p.name} className="rounded-2xl border border-slate-100 bg-white p-3 text-xs shadow-sm">
                {p.name}
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-xl font-medium">Empresas</h2>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {empresas.map((p) => (
              <div key={p.name} className="rounded-2xl border border-slate-100 bg-white p-3 text-xs shadow-sm">
                {p.name}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-[#0A2A6B] px-6 py-10 text-center text-white">
        <h2 className="text-2xl font-medium">¿Necesitas atención inmediata?</h2>
        <p className="mt-2 text-sm text-white/80">Agenda por WhatsApp en minutos.</p>
        <button
          type="button"
          onClick={() => openModal()}
          className="btn-green-gradient mt-6 rounded-full px-5 py-2.5 text-xs font-medium text-white"
        >
          Solicitar atención
        </button>
      </section>
    </div>
  );
}
