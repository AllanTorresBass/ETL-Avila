import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppointmentModal } from "./components/AppointmentModal";
import { SiteFooter } from "./components/SiteFooter";
import { SiteHeader } from "./components/SiteHeader";
import { Splash } from "./components/Splash";
import { WhatsAppFab } from "./components/WhatsAppFab";
import { AppointmentProvider } from "./context/AppointmentContext";
import { ContactoPage } from "./pages/ContactoPage";
import { EquipoMedicoPage } from "./pages/EquipoMedicoPage";
import { HomePage } from "./pages/HomePage";
import { NosotrosPage } from "./pages/NosotrosPage";
import { ServiciosPage } from "./pages/ServiciosPage";

function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (hash) {
        const el = document.querySelector(hash);
        if (el) {
          el.scrollIntoView({ behavior: "smooth" });
          return;
        }
      }
      window.scrollTo(0, 0);
    }, 100);
    return () => window.clearTimeout(t);
  }, [pathname, hash]);
  return null;
}

function Shell() {
  return (
    <AppointmentProvider>
      <Splash />
      <SiteHeader />
      <ScrollManager />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/nosotros" element={<NosotrosPage />} />
          <Route path="/servicios" element={<ServiciosPage />} />
          <Route path="/equipo-medico" element={<EquipoMedicoPage />} />
          <Route path="/contacto" element={<ContactoPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <SiteFooter />
      <WhatsAppFab />
      <AppointmentModal />
    </AppointmentProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
