import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Montserrat } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

const montserrat = Montserrat({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Ávila GPS · Inventario de facturas",
  description: "Lector interno de personas, facturas y documentos personales",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/sign-in"
      appearance={{
        variables: {
          colorPrimary: "#0F7A33",
          borderRadius: "1rem",
        },
      }}
    >
      <html lang="es" className={`${montserrat.variable} h-full antialiased`}>
        <body className="min-h-full bg-[#F4F8FC] font-sans text-[#0A2A6B] selection:bg-[#6CC24A] selection:text-white">
          <SiteHeader />
          <main className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">{children}</main>
          <footer className="bg-[#0A1F4D] px-4 py-6 text-center text-xs text-white/80 sm:px-6">
            Ávila GPS · Lector interno. No compartir rutas de respaldo con nombres de pacientes.
          </footer>
        </body>
      </html>
    </ClerkProvider>
  );
}
