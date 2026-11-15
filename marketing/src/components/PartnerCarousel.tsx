import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { PARTNERS } from "../data/content";

type Filter = "Todos" | "Aseguradoras" | "Empresas";

const PAGE = 4;

export function PartnerCarousel() {
  const [filter, setFilter] = useState<Filter>("Todos");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (filter === "Aseguradoras") return PARTNERS.filter((p) => p.sector.includes("Aseguradora"));
    if (filter === "Empresas") return PARTNERS.filter((p) => !p.sector.includes("Aseguradora"));
    return [...PARTNERS];
  }, [filter]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const safePage = filtered.length === 0 ? 0 : page % pages;
  const slice = filtered.slice(safePage * PAGE, safePage * PAGE + PAGE);

  function setFilterAndReset(f: Filter) {
    setFilter(f);
    setPage(0);
  }

  return (
    <section id="aseguradoras-empresas" className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-3xl font-medium tracking-tight sm:text-4xl">Compañías Aseguradoras y Empresas</h2>
          <p className="mt-2 text-sm text-slate-500">Convenios activos con aseguradoras y organizaciones aliadas.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(["Todos", "Aseguradoras", "Empresas"] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilterAndReset(f)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                filter === f ? "bg-[#033CA0] text-white" : "border border-slate-200 bg-white text-slate-600"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
          <p className="font-medium">No se encontraron convenios</p>
          <p className="mt-1 text-sm text-slate-500">Intenta cambiar el filtro de sector.</p>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {slice.map((p) => (
              <article
                key={p.name}
                className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <p className="text-sm font-medium">{p.name}</p>
                <p className="mt-1 text-xs text-slate-500">{p.sector}</p>
              </article>
            ))}
          </div>
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              aria-label="Anterior"
              className="rounded-full border border-slate-200 bg-white p-2"
              onClick={() => setPage((p) => (p - 1 + pages) % pages)}
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex gap-1.5">
              {Array.from({ length: pages }).map((_, i) => (
                <button
                  key={i}
                  type="button"
                  aria-label={`Página ${i + 1}`}
                  onClick={() => setPage(i)}
                  className={`h-2 rounded-full transition ${
                    i === safePage ? "w-6 bg-[#6CC24A]" : "w-2 bg-slate-300"
                  }`}
                />
              ))}
            </div>
            <button
              type="button"
              aria-label="Siguiente"
              className="rounded-full border border-slate-200 bg-white p-2"
              onClick={() => setPage((p) => (p + 1) % pages)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </>
      )}
    </section>
  );
}
