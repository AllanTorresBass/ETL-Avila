import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function PersonasPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const { q = "", page: pageRaw } = await searchParams;
  const page = parsePage(pageRaw);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();
  const query = q.trim();
  const like = `%${query}%`;

  const [countRow] = query
    ? await db`
        SELECT count(DISTINCT p.id)::int AS n
        FROM avila.person p
        LEFT JOIN avila.authorization_line al ON al.person_id = p.id
        WHERE p.identity_number ILIKE ${like}
           OR coalesce(p.full_name, '') ILIKE ${like}
           OR coalesce(p.phone, '') ILIKE ${like}
           OR coalesce(al.clave_rms, '') ILIKE ${like}
      `
    : await db`SELECT count(*)::int AS n FROM avila.person`;

  const total = countRow?.n ?? 0;

  const people = query
    ? await db`
        SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
               p.phone, p.birth_date,
               coalesce(dc.docs, 0)::int AS docs
        FROM avila.person p
        LEFT JOIN (
          SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
        ) dc ON dc.person_id = p.id
        WHERE p.id IN (
          SELECT p2.id FROM avila.person p2
          LEFT JOIN avila.authorization_line al ON al.person_id = p2.id
          WHERE p2.identity_number ILIKE ${like}
             OR coalesce(p2.full_name, '') ILIKE ${like}
             OR coalesce(p2.phone, '') ILIKE ${like}
             OR coalesce(al.clave_rms, '') ILIKE ${like}
        )
        ORDER BY p.identity_number NULLS LAST
        LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
      `
    : await db`
        SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
               p.phone, p.birth_date,
               coalesce(dc.docs, 0)::int AS docs
        FROM avila.person p
        LEFT JOIN (
          SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
        ) dc ON dc.person_id = p.id
        ORDER BY p.created_at DESC
        LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
      `;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Personas"
        description="Cliente = titular o beneficiario. Busca por cédula, nombre, teléfono o clave RMS."
      />
      <form className="flex max-w-md flex-wrap gap-2">
        <label className="sr-only" htmlFor="q">
          Buscar personas
        </label>
        <Input
          id="q"
          name="q"
          defaultValue={q}
          placeholder="Cédula, nombre, teléfono o clave"
          className="rounded-xl border-slate-200"
        />
        <button type="submit" className="btn-green-gradient rounded-full px-5 py-2 text-xs font-medium text-white">
          Buscar
        </button>
      </form>
      <ResultCount shown={people.length} total={total} />
      {people.length === 0 ? (
        <EmptyState
          title="No se encontraron personas"
          hint="Intenta cambiar los términos de búsqueda o ejecuta la carga de documentos."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {people.map((person) => (
            <Link key={person.id} href={`/personas/${person.id}`}>
              <Card className="rounded-3xl border-slate-100 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                <CardContent className="p-5">
                  <div className="text-sm font-medium">{person.full_name || "Sin nombre en OCR"}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {person.identity_type}: {person.identity_number || "—"}
                  </div>
                  {(person.phone || person.birth_date) && (
                    <div className="mt-1 text-xs text-slate-500">
                      {person.phone || "Sin teléfono"}
                      {person.birth_date
                        ? ` · ${String(person.birth_date).slice(0, 10)}`
                        : ""}
                    </div>
                  )}
                  <div className="mt-3 text-xs text-[#033CA0]">{person.docs} documentos</div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <Pagination
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={total}
        basePath="/personas"
        searchParams={{ q: query || undefined }}
      />
    </div>
  );
}
