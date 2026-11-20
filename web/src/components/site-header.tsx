"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { can, ACCESS_ROLE_LABELS, type Permission } from "@/lib/access";
import type { SessionUser } from "@/lib/session-db";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { signOut } from "@/app/sign-in/actions";

const links: { href: string; label: string; permission: Permission }[] = [
  { href: "/etl", label: "ETL", permission: "read" },
  { href: "/bi", label: "Negocio", permission: "read" },
  { href: "/informe", label: "Informe", permission: "read" },
  { href: "/personas", label: "Personas", permission: "read" },
  { href: "/facturas", label: "Facturas", permission: "read" },
  { href: "/documentos", label: "Documentos", permission: "read" },
  { href: "/revision", label: "Revisión", permission: "review" },
  { href: "/usuarios", label: "Acceso", permission: "manage_users" },
];

function NavLinks({ role, onNavigate }: { role: SessionUser["role"]; onNavigate?: () => void }) {
  const pathname = usePathname();
  const visible = links.filter((link) => can(role, link.permission));
  return (
    <>
      {visible.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={`inline-flex min-h-10 items-center rounded-full px-4 text-sm font-medium transition-colors ${
              active
                ? "bg-brand/10 text-brand"
                : "text-muted-foreground hover:bg-brand/10 hover:text-brand"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </>
  );
}

export function SiteHeader({ user }: { user: SessionUser | null }) {
  const pathname = usePathname();
  const onSignIn = pathname === "/sign-in" || pathname.startsWith("/sign-in/");

  return (
    <header className="sticky top-3 z-40 mx-4 sm:mx-6">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 rounded-full border border-border bg-card/80 px-4 py-1.5 shadow-sm backdrop-blur-md sm:px-5">
        <Link
          href={user ? "/etl" : "/sign-in"}
          className="flex items-center gap-2 rounded-full text-sm font-semibold tracking-tight text-foreground"
        >
          <span aria-hidden="true" className="size-2.5 rounded-full bg-primary" />
          Ávila GPS
          <span className="font-normal text-muted-foreground">· Lector</span>
        </Link>
        {user ? (
          <nav className="hidden items-center gap-1 md:flex" aria-label="Principal">
            <NavLinks role={user.role} />
          </nav>
        ) : null}
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {user ? (
            <>
              <span className="hidden rounded-full bg-brand/10 px-3 py-1 text-xs font-medium text-brand sm:inline">
                {ACCESS_ROLE_LABELS[user.role]}
              </span>
              <form action={signOut}>
                <button
                  type="submit"
                  className="min-h-10 rounded-full border border-border px-4 text-sm font-medium text-brand"
                >
                  Salir
                </button>
              </form>
            </>
          ) : onSignIn ? null : (
            <Link
              href="/sign-in"
              className="min-h-10 rounded-full border border-border px-4 py-2 text-sm font-medium text-brand"
            >
              Entrar
            </Link>
          )}
          {user ? (
            <Sheet>
              <SheetTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="rounded-full md:hidden"
                  aria-label="Abrir menú"
                >
                  <Menu className="h-4 w-4" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="rounded-l-3xl">
                <SheetHeader>
                  <SheetTitle className="text-foreground">Navegación</SheetTitle>
                </SheetHeader>
                <p className="mt-2 text-sm text-muted-foreground">{user.email}</p>
                <nav className="mt-4 flex flex-col gap-2" aria-label="Móvil">
                  <NavLinks role={user.role} />
                </nav>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  );
}
