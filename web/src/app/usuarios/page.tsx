import type { Metadata } from "next";
import { ACCESS_ROLE_HINTS, ACCESS_ROLE_LABELS, APP_ROLES, type AppRole } from "@/lib/access";
import { requirePermission } from "@/lib/auth";
import { sql } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { createUser, updateUser } from "./actions";

export const metadata: Metadata = {
  title: "Acceso · Ávila GPS",
};

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  datos: "Revisa el correo y el rol.",
  password: "La contraseña necesita entre 8 y 200 caracteres.",
  duplicate: "Ese correo ya tiene cuenta.",
  self: "No puedes desactivar tu propia cuenta.",
  last: "Tiene que quedar al menos un super admin activo.",
};

type UserRow = {
  id: string;
  email: string;
  full_name: string | null;
  role: AppRole;
  active: boolean;
};

const fieldClass =
  "mt-1 block w-full rounded-xl border border-border bg-card px-4 py-2.5 text-sm text-foreground";

export default async function UsuariosPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; ok?: string }>;
}) {
  const actor = await requirePermission("manage_users");
  const sp = await searchParams;
  const db = sql();
  const users = (await db`
    SELECT id::text AS id, email, full_name, role, active
    FROM avila.app_user
    ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'revisor' THEN 1 ELSE 2 END, email
  `) as UserRow[];

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Personal"
        title="Acceso"
        description="Las cuentas entran con correo y contraseña. El rol decide qué puede abrir cada persona."
      />

      <section className="grid gap-3 sm:grid-cols-3">
        {APP_ROLES.map((role) => (
          <article key={role} className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <p className="text-sm font-medium">{ACCESS_ROLE_LABELS[role]}</p>
            <p className="mt-1 text-sm text-muted-foreground">{ACCESS_ROLE_HINTS[role]}</p>
          </article>
        ))}
      </section>

      {sp.error && ERRORS[sp.error] ? (
        <p role="alert" className="rounded-2xl bg-danger-soft px-4 py-3 text-sm text-danger">
          {ERRORS[sp.error]}
        </p>
      ) : null}
      {sp.ok ? (
        <p role="status" className="rounded-2xl bg-success-soft px-4 py-3 text-sm text-success">
          {sp.ok === "creada" ? "Cuenta creada." : "Cuenta actualizada."}
        </p>
      ) : null}

      <section className="rounded-3xl border border-border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-medium">Nueva cuenta</h2>
        <form action={createUser} className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="block text-xs font-medium text-muted-foreground">
            Nombre
            <input name="full_name" autoComplete="name" className={fieldClass} />
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Correo
            <input name="email" type="email" required autoComplete="off" className={fieldClass} />
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Contraseña
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Rol
            <select name="role" defaultValue="lector" className={fieldClass} aria-label="Rol">
              {APP_ROLES.map((role) => (
                <option key={role} value={role}>
                  {ACCESS_ROLE_LABELS[role]}
                </option>
              ))}
            </select>
          </label>
          <div className="sm:col-span-2">
            <button
              type="submit"
              className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
            >
              Crear cuenta
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Cuentas</h2>
        {users.map((user) => (
          <article key={user.id} className="rounded-3xl border border-border bg-card p-6 shadow-sm">
            <form action={updateUser} className="grid gap-4 sm:grid-cols-2">
              <input type="hidden" name="id" value={user.id} />
              <label className="block text-xs font-medium text-muted-foreground">
                Nombre
                <input
                  name="full_name"
                  defaultValue={user.full_name || ""}
                  className={fieldClass}
                />
              </label>
              <label className="block text-xs font-medium text-muted-foreground">
                Correo
                <input value={user.email} readOnly className={`${fieldClass} text-muted-foreground`} />
              </label>
              <label className="block text-xs font-medium text-muted-foreground">
                Rol
                <select
                  name="role"
                  defaultValue={user.role}
                  className={fieldClass}
                  aria-label={`Rol de ${user.email}`}
                >
                  {APP_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {ACCESS_ROLE_LABELS[role]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium text-muted-foreground">
                Nueva contraseña
                <input
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Sin cambio"
                  className={fieldClass}
                />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="active"
                  value="1"
                  defaultChecked={user.active}
                  className="size-4 accent-primary"
                />
                Activa
                {user.id === actor.id ? (
                  <span className="text-xs text-muted-foreground">· esta sesión</span>
                ) : null}
              </label>
              <div className="flex items-end">
                <button
                  type="submit"
                  className="rounded-full border border-border px-5 py-2.5 text-xs font-medium text-brand"
                >
                  Guardar
                </button>
              </div>
            </form>
          </article>
        ))}
      </section>
    </div>
  );
}
