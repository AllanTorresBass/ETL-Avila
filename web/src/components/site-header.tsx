"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

const links = [
  { href: "/", label: "Inicio" },
  { href: "/personas", label: "Personas" },
  { href: "/facturas", label: "Facturas" },
  { href: "/documentos", label: "Documentos" },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <>
      {links.map((link) => {
        const active =
          link.href === "/"
            ? pathname === "/"
            : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              active
                ? "bg-[#033CA0]/10 text-[#033CA0]"
                : "text-slate-600 hover:bg-[#033CA0]/10 hover:text-[#033CA0]"
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
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 rounded-full border border-white/70 bg-white/70 px-4 py-2 shadow-sm backdrop-blur-md sm:px-5">
        <Link href="/" className="text-sm font-semibold tracking-tight text-[#0A2A6B]">
          Ávila GPS · ETL
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
                className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-[#033CA0]"
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
                <SheetTitle className="text-[#0A2A6B]">Navegación</SheetTitle>
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
