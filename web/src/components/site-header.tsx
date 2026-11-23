"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  ChevronDown,
  ClipboardCheck,
  FileCheck,
  FileStack,
  FileText,
  Layers,
  LogOut,
  Menu,
  Receipt,
  Shield,
  FlaskConical,
  Stethoscope,
  Users,
  type LucideIcon,
} from "lucide-react";
import { DropdownMenu } from "radix-ui";
import {
  can,
  ACCESS_ROLE_HINTS,
  ACCESS_ROLE_LABELS,
  type AppRole,
  type Permission,
} from "@/lib/access";
import type { SessionUser } from "@/lib/session-db";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { signOut } from "@/app/sign-in/actions";

interface Destination {
  href: string;
  label: string;
  hint: string;
  permission: Permission;
  icon: LucideIcon;
}

interface MenuEntry {
  kind: "menu";
  id: string;
  label: string;
  description: string;
  items: Destination[];
}

interface LinkEntry {
  kind: "link";
  item: Destination;
  separated?: boolean;
}

type NavEntry = MenuEntry | LinkEntry;

const ETL: Destination = {
  href: "/etl",
  label: "ETL",
  hint: "Operación del pipeline",
  permission: "read",
  icon: Activity,
};
const NEGOCIO: Destination = {
  href: "/bi",
  label: "Negocio",
  hint: "Indicadores del negocio",
  permission: "read",
  icon: BarChart3,
};
const INFORME: Destination = {
  href: "/informe",
  label: "Informe",
  hint: "Resumen del archivo",
  permission: "read",
  icon: FileText,
};
const PERSONAS: Destination = {
  href: "/personas",
  label: "Personas",
  hint: "Titulares y beneficiarios",
  permission: "read",
  icon: Users,
};
const FACTURAS: Destination = {
  href: "/facturas",
  label: "Facturas",
  hint: "Paquetes de facturas",
  permission: "read",
  icon: Receipt,
};
const AUTORIZACIONES: Destination = {
  href: "/autorizaciones",
  label: "Autorizaciones",
  hint: "Libros de las aseguradoras",
  permission: "read",
  icon: FileCheck,
};
const MEDICOS: Destination = {
  href: "/medicos",
  label: "Médicos",
  hint: "Directorio clínico",
  permission: "read",
  icon: Stethoscope,
};
const ESTUDIOS: Destination = {
  href: "/estudios",
  label: "Estudios",
  hint: "Pruebas diagnósticas",
  permission: "read",
  icon: FlaskConical,
};
const ESPECIALIDADES: Destination = {
  href: "/especialidades",
  label: "Especialidades",
  hint: "Especialidades y sus médicos",
  permission: "read",
  icon: Layers,
};
const DOCUMENTOS: Destination = {
  href: "/documentos",
  label: "Documentos",
  hint: "Archivos del paquete",
  permission: "read",
  icon: FileStack,
};
const REVISION: Destination = {
  href: "/revision",
  label: "Revisión",
  hint: "Casos por confirmar",
  permission: "review",
  icon: ClipboardCheck,
};
const ACCESO: Destination = {
  href: "/usuarios",
  label: "Acceso",
  hint: "Cuentas y roles",
  permission: "manage_users",
  icon: Shield,
};

const PANEL_COPY = "Pipeline, negocio y resumen.";
const CLINICA_COPY = "Directorio, pruebas y especialidades.";

const ENTRIES: NavEntry[] = [
  { kind: "menu", id: "paneles", label: "Paneles", description: PANEL_COPY, items: [ETL, NEGOCIO, INFORME] },
  { kind: "link", item: PERSONAS },
  { kind: "link", item: FACTURAS },
  { kind: "link", item: AUTORIZACIONES },
  { kind: "menu", id: "clinica", label: "Clínica", description: CLINICA_COPY, items: [MEDICOS, ESTUDIOS, ESPECIALIDADES] },
  { kind: "link", item: DOCUMENTOS },
  { kind: "link", item: REVISION, separated: true },
];

const SECTIONS: { id: string; label: string; description?: string; items: Destination[] }[] = [
  { id: "paneles", label: "Paneles", description: PANEL_COPY, items: [ETL, NEGOCIO, INFORME] },
  { id: "registros", label: "Registros", items: [PERSONAS, FACTURAS, AUTORIZACIONES, DOCUMENTOS] },
  { id: "clinica", label: "Clínica", description: CLINICA_COPY, items: [MEDICOS, ESTUDIOS, ESPECIALIDADES] },
  { id: "trabajo", label: "Trabajo", items: [REVISION] },
];

const menuContentClass =
  "z-50 min-w-80 origin-(--radix-dropdown-menu-content-transform-origin) overflow-hidden rounded-3xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg data-[side=bottom]:slide-in-from-top-2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95";

const menuItemClass =
  "flex cursor-pointer items-center gap-3 rounded-2xl px-2 py-2 text-left outline-none select-none data-[highlighted]:bg-brand/10";

function isCurrent(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function entriesFor(role: AppRole): NavEntry[] {
  const visible: NavEntry[] = [];
  for (const entry of ENTRIES) {
    if (entry.kind === "link") {
      if (can(role, entry.item.permission)) visible.push(entry);
      continue;
    }
    const items = entry.items.filter((item) => can(role, item.permission));
    if (items.length > 1) visible.push({ ...entry, items });
    else if (items.length === 1) visible.push({ kind: "link", item: items[0] });
  }
  return visible;
}

function sectionsFor(role: AppRole) {
  return SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => can(role, item.permission)),
  })).filter((section) => section.items.length > 0);
}

function initials(user: SessionUser) {
  const source = user.fullName?.trim() || user.email;
  const parts = source.split(/\s+/).filter(Boolean);
  const first = parts[0] ?? source;
  const second = parts[1];
  if (second) return `${first.charAt(0)}${second.charAt(0)}`.toUpperCase();
  return first.slice(0, 2).toUpperCase();
}

function DestinationBody({ item, active }: { item: Destination; active: boolean }) {
  const Icon = item.icon;
  return (
    <>
      <span
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-xl",
          active ? "bg-brand/15 text-brand" : "bg-secondary text-brand",
        )}
      >
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-sm font-medium", active ? "text-brand" : "text-foreground")}>
          {item.label}
        </span>
        <span className="block text-xs text-muted-foreground">{item.hint}</span>
      </span>
      {active ? (
        <span
          aria-hidden="true"
          className="shrink-0 rounded-full bg-brand/15 px-2 py-0.5 text-[11px] font-medium text-brand"
        >
          Actual
        </span>
      ) : null}
    </>
  );
}

function MenuItems({
  items,
  pathname,
  onNavigate,
}: {
  items: Destination[];
  pathname: string;
  onNavigate?: () => void;
}) {
  return items.map((item) => {
    const active = isCurrent(pathname, item.href);
    return (
      <DropdownMenu.Item key={item.href} asChild>
        <Link
          href={item.href}
          onClick={onNavigate}
          aria-current={active ? "page" : undefined}
          className={cn(menuItemClass, active && "bg-brand/10")}
        >
          <DestinationBody item={item} active={active} />
        </Link>
      </DropdownMenu.Item>
    );
  });
}

function NavSplit({ entry, pathname }: { entry: MenuEntry; pathname: string }) {
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === pathname;
  const activeItem = entry.items.find((item) => isCurrent(pathname, item.href));
  const active = Boolean(activeItem);

  return (
    <DropdownMenu.Root open={open} onOpenChange={(next) => setOpenPath(next ? pathname : null)}>
      <DropdownMenu.Trigger
        type="button"
        className={cn(
          "group inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-full px-3.5 text-sm font-medium whitespace-nowrap outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
          active || open ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-brand/10 hover:text-brand",
        )}
      >
        <span>{entry.label}</span>
        {activeItem ? (
          <span className="hidden font-normal opacity-80 xl:inline">
            <span aria-hidden="true"> · </span>
            {activeItem.label}
          </span>
        ) : null}
        {activeItem ? <span className="sr-only xl:hidden">, página actual: {activeItem.label}</span> : null}
        <ChevronDown
          className="size-3.5 opacity-70 transition-transform group-data-[state=open]:rotate-180"
          aria-hidden="true"
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={10} className={menuContentClass}>
          <DropdownMenu.Label className="px-3 pt-2.5 pb-2">
            <span className="block text-sm font-semibold tracking-tight text-foreground">{entry.label}</span>
            <span className="mt-0.5 block text-xs font-normal text-muted-foreground">{entry.description}</span>
          </DropdownMenu.Label>
          <DropdownMenu.Separator className="mx-2 mb-1 h-px bg-border" />
          <MenuItems items={entry.items} pathname={pathname} onNavigate={() => setOpenPath(null)} />
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function NavLink({ item, pathname }: { item: Destination; pathname: string }) {
  const active = isCurrent(pathname, item.href);
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex min-h-10 items-center rounded-full px-3.5 text-sm font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-brand/10 hover:text-brand",
      )}
    >
      {item.label}
    </Link>
  );
}

function DesktopNav({ role }: { role: AppRole }) {
  const pathname = usePathname();
  const entries = entriesFor(role);
  return (
    <nav className="hidden min-w-0 items-center gap-0.5 lg:flex" aria-label="Principal">
      {entries.map((entry, index) => {
        if (entry.kind === "menu") {
          return <NavSplit key={entry.id} entry={entry} pathname={pathname} />;
        }
        return (
          <span key={entry.item.href} className="inline-flex items-center">
            {entry.separated && index > 0 ? (
              <span aria-hidden="true" className="mx-1.5 h-5 w-px bg-border" />
            ) : null}
            <NavLink item={entry.item} pathname={pathname} />
          </span>
        );
      })}
    </nav>
  );
}

function MobileSections({ role, onNavigate }: { role: AppRole; onNavigate: () => void }) {
  const pathname = usePathname();
  const sections = sectionsFor(role);
  const showAcceso = can(role, ACCESO.permission);
  return (
    <>
      <nav className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 pb-2" aria-label="Móvil">
        {sections.map((section) => (
          <div key={section.id}>
            <p className="px-2 pb-1 text-[11px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
              {section.label}
            </p>
            {section.description ? (
              <p className="px-2 pb-1.5 text-xs text-muted-foreground">{section.description}</p>
            ) : null}
            <div className="flex flex-col">
              {section.items.map((item) => {
                const active = isCurrent(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex min-h-11 items-center gap-3 rounded-2xl px-2 py-1.5",
                      active ? "bg-brand/10" : "hover:bg-brand/10",
                    )}
                  >
                    <DestinationBody item={item} active={active} />
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <SheetFooter className="border-t border-border">
        {showAcceso ? (
          <Link
            href={ACCESO.href}
            onClick={onNavigate}
            aria-current={isCurrent(pathname, ACCESO.href) ? "page" : undefined}
            className={cn(
              "flex min-h-11 items-center gap-3 rounded-2xl px-2 py-1.5",
              isCurrent(pathname, ACCESO.href) ? "bg-brand/10" : "hover:bg-brand/10",
            )}
          >
            <DestinationBody item={ACCESO} active={isCurrent(pathname, ACCESO.href)} />
          </Link>
        ) : null}
        <form action={signOut}>
          <button
            type="submit"
            className="flex min-h-11 w-full items-center gap-3 rounded-2xl px-2 py-1.5 text-left hover:bg-brand/10"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-secondary text-brand">
              <LogOut className="size-4" aria-hidden="true" />
            </span>
            <span className="text-sm font-medium text-foreground">Salir</span>
          </button>
        </form>
      </SheetFooter>
    </>
  );
}

function AccountMenu({ user }: { user: SessionUser }) {
  const pathname = usePathname();
  const showAcceso = can(user.role, ACCESO.permission);
  const accesoActive = isCurrent(pathname, ACCESO.href);
  const roleLabel = ACCESS_ROLE_LABELS[user.role];

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        type="button"
        className="inline-flex min-h-10 items-center gap-2 rounded-full bg-brand/10 py-1 pr-2.5 pl-1 text-xs font-medium text-brand outline-none transition-colors hover:bg-brand/15 focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-brand/15"
      >
        <span
          aria-hidden="true"
          className="grid size-7 place-items-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground"
        >
          {initials(user)}
        </span>
        <span className="sr-only">Cuenta, </span>
        <span className="max-xl:sr-only">{roleLabel}</span>
        <ChevronDown className="size-3.5 opacity-70" aria-hidden="true" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={10} className={menuContentClass}>
          <DropdownMenu.Label className="px-3 py-2">
            <span className="block text-sm font-medium text-foreground">{user.fullName?.trim() || "Cuenta"}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{user.email}</span>
            <span className="mt-1 block text-xs font-medium text-brand">{roleLabel}</span>
            <span className="block text-xs text-muted-foreground">{ACCESS_ROLE_HINTS[user.role]}</span>
          </DropdownMenu.Label>
          {showAcceso ? (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border" />
              <DropdownMenu.Item asChild>
                <Link
                  href={ACCESO.href}
                  aria-current={accesoActive ? "page" : undefined}
                  className={menuItemClass}
                >
                  <DestinationBody item={ACCESO} active={accesoActive} />
                </Link>
              </DropdownMenu.Item>
            </>
          ) : null}
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <form action={signOut}>
            <DropdownMenu.Item asChild>
              <button type="submit" className={cn(menuItemClass, "w-full")}>
                <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-secondary text-brand">
                  <LogOut className="size-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-foreground">Salir</span>
                  <span className="block text-xs text-muted-foreground">Cerrar la sesión</span>
                </span>
                <span className="size-4 shrink-0" />
              </button>
            </DropdownMenu.Item>
          </form>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export interface SiteHeaderProps {
  user: SessionUser | null;
}

export function SiteHeader({ user }: SiteHeaderProps) {
  const pathname = usePathname();
  const onSignIn = pathname === "/sign-in" || pathname.startsWith("/sign-in/");
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-3 z-40 mx-4 sm:mx-6">
      <div className="mx-auto flex max-w-6xl items-center gap-3 rounded-full border border-border bg-card/80 px-3 py-1.5 shadow-sm backdrop-blur-md sm:px-4">
        <Link
          href={user ? "/etl" : "/sign-in"}
          className="flex shrink-0 items-center gap-2 rounded-full text-sm font-semibold tracking-tight whitespace-nowrap text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span aria-hidden="true" className="size-2.5 rounded-full bg-primary" />
          Ávila GPS
          <span className="font-normal text-muted-foreground">· Lector</span>
        </Link>
        {user ? <DesktopNav role={user.role} /> : null}
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <ThemeToggle />
          {user ? (
            <>
              <div className="hidden lg:block">
                <AccountMenu user={user} />
              </div>
              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className="rounded-full lg:hidden"
                    aria-label="Abrir menú"
                  >
                    <Menu className="h-4 w-4" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" className="w-full rounded-l-3xl sm:max-w-sm">
                  <SheetHeader className="pr-10">
                    <SheetTitle className="text-foreground">Ávila GPS</SheetTitle>
                    <p className="truncate text-sm text-muted-foreground">{user.email}</p>
                    <p className="text-xs font-medium text-brand">{ACCESS_ROLE_LABELS[user.role]}</p>
                  </SheetHeader>
                  <MobileSections role={user.role} onNavigate={() => setMobileOpen(false)} />
                </SheetContent>
              </Sheet>
            </>
          ) : onSignIn ? null : (
            <Link
              href="/sign-in"
              className="inline-flex min-h-10 items-center rounded-full border border-border px-4 text-sm font-medium text-brand"
            >
              Entrar
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
