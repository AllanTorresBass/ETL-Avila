import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type AppointmentState = {
  open: boolean;
  service?: string;
  specialist?: string;
  openModal: (opts?: { service?: string; specialist?: string }) => void;
  closeModal: () => void;
};

const AppointmentContext = createContext<AppointmentState | null>(null);

export function AppointmentProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [service, setService] = useState<string | undefined>();
  const [specialist, setSpecialist] = useState<string | undefined>();

  const openModal = useCallback((opts?: { service?: string; specialist?: string }) => {
    setService(opts?.service);
    setSpecialist(opts?.specialist);
    setOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setOpen(false);
  }, []);

  const value = useMemo(
    () => ({ open, service, specialist, openModal, closeModal }),
    [open, service, specialist, openModal, closeModal],
  );

  return <AppointmentContext.Provider value={value}>{children}</AppointmentContext.Provider>;
}

export function useAppointment() {
  const ctx = useContext(AppointmentContext);
  if (!ctx) throw new Error("useAppointment must be used within AppointmentProvider");
  return ctx;
}
