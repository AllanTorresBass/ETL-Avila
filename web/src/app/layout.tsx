import type { Metadata } from "next";
import { Montserrat } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { getCurrentUser } from "@/lib/session";
import "./globals.css";

const montserrat = Montserrat({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Ávila GPS · Inventario de facturas",
  description: "Lector interno de personas, facturas y documentos personales",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const user = await getCurrentUser();
  return (
      <html lang="es" className={`${montserrat.variable} h-full antialiased`} suppressHydrationWarning>
        <head>
          <script
            dangerouslySetInnerHTML={{
              __html:
                "try{var r=document.documentElement,m=window.matchMedia('(prefers-color-scheme: dark)'),s=function(){try{return localStorage.getItem('theme')}catch(e){return null}},f=function(){var t=s(),d=t==='dark'||(t!=='light'&&m.matches);r.classList.toggle('dark',d);r.style.colorScheme=d?'dark':'light'};f();m.addEventListener('change',function(){if(!s())f()})}catch(e){}",
            }}
          />
        </head>
        <body
          className="min-h-full bg-background font-sans text-foreground selection:bg-primary selection:text-primary-foreground"
          suppressHydrationWarning
        >
          <a
            href="#contenido"
            className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-full focus:bg-hero focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-hero-foreground"
          >
            Saltar al contenido
          </a>
          <SiteHeader user={user} />
          <main id="contenido" className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">
            {children}
          </main>
          <footer className="bg-hero px-4 py-6 text-center text-sm text-hero-foreground/80 sm:px-6">
            Ávila GPS · Lector interno. No compartir rutas de respaldo con nombres de pacientes.
          </footer>
        </body>
      </html>
  );
}
