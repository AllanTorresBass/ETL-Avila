"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

const links = [
  { href: "/etl", label: "ETL" },
  { href: "/bi", label: "Negocio" },
  { href: "/personas", label: "Personas" },
  { href: "/facturas", label: "Facturas" },
  { href: "/documentos", label: "Documentos" },
  { href: "/revision", label: "Revisión" },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <>
      {links.map((link) => {
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

export function SiteHeader() {
  return (
    <header className="sticky top-3 z-40 mx-4 sm:mx-6">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 rounded-full border border-border bg-card/80 px-4 py-1.5 shadow-sm backdrop-blur-md sm:px-5">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-full text-sm font-semibold tracking-tight text-foreground"
        >
          <span aria-hidden="true" className="size-2.5 rounded-full bg-primary" />
          Ávila GPS
          <span className="font-normal text-muted-foreground">· Lector</span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Principal">
          <NavLinks />
        </nav>
        <div className="flex items-center gap-2">
          <Show when="signed-in">
            <UserButton />
          </Show>
          <Show when="signed-out">
            <SignInButton mode="redirect">
              <button
                type="button"
                className="min-h-10 rounded-full border border-border px-4 text-sm font-medium text-brand"
              >
                Entrar
              </button>
            </SignInButton>
          </Show>
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
              <nav className="mt-4 flex flex-col gap-2" aria-label="Móvil">
                <NavLinks />
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
