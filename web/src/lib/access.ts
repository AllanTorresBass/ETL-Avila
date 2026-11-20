export const APP_ROLES = ["super_admin", "revisor", "lector"] as const;

export type AppRole = (typeof APP_ROLES)[number];

export type Permission = "read" | "review" | "manage_users";

const ROLE_PERMISSIONS: Record<AppRole, readonly Permission[]> = {
  super_admin: ["read", "review", "manage_users"],
  revisor: ["read", "review"],
  lector: ["read"],
};

export const ACCESS_ROLE_LABELS: Record<AppRole, string> = {
  super_admin: "Super admin",
  revisor: "Revisor",
  lector: "Lector",
};

export const ACCESS_ROLE_HINTS: Record<AppRole, string> = {
  super_admin: "Lectura, revisión y cuentas",
  revisor: "Lectura y revisión",
  lector: "Solo lectura",
};

export function isAppRole(value: unknown): value is AppRole {
  return typeof value === "string" && (APP_ROLES as readonly string[]).includes(value);
}

export function can(role: AppRole, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role].includes(permission);
}

/** Route gate used by the proxy and by the sign-in redirect. */
export function canAccessPath(role: AppRole, pathname: string): boolean {
  if (
    pathname === "/usuarios" ||
    pathname.startsWith("/usuarios/") ||
    pathname === "/api/v1/usuarios" ||
    pathname.startsWith("/api/v1/usuarios/")
  ) {
    return can(role, "manage_users");
  }
  if (
    pathname === "/revision" ||
    pathname.startsWith("/revision/") ||
    pathname === "/api/v1/revision" ||
    pathname.startsWith("/api/v1/revision/")
  ) {
    return can(role, "review");
  }
  return can(role, "read");
}
