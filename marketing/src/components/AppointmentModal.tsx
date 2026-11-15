import confetti from "canvas-confetti";
import { X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useReducedMotion } from "framer-motion";
import { APPOINTMENT_SERVICES, DOCTORS } from "../data/content";
import { useAppointment } from "../context/AppointmentContext";
import { cedulaHint, isValidPhone, openWhatsApp, whatsAppHref } from "../lib/whatsapp";

export function AppointmentModal() {
  const { open, service, specialist, closeModal } = useAppointment();
  const reduceMotion = useReducedMotion();
  const [servicio, setServicio] = useState("");
  const [modalidad, setModalidad] = useState<"En el Hogar" | "En Consultorio">("En Consultorio");
  const [nombre, setNombre] = useState("");
  const [telefono, setTelefono] = useState("");
  const [cedula, setCedula] = useState("");
  const [fecha, setFecha] = useState("");
  const [especialista, setEspecialista] = useState("Triaje por Ávila GPS");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [waMessage, setWaMessage] = useState("");
  const [popupBlocked, setPopupBlocked] = useState(false);

  useEffect(() => {
    if (!open) {
      setSubmitted(false);
      setPopupBlocked(false);
      setErrors({});
      return;
    }
    if (service) setServicio(service);
    if (specialist) setEspecialista(specialist);
  }, [open, service, specialist]);

  if (!open) return null;

  function validate() {
    const next: Record<string, string> = {};
    if (!servicio) next.servicio = "Selecciona un servicio";
    if (!nombre.trim()) next.nombre = "Indica el nombre del paciente";
    if (!telefono.trim()) next.telefono = "Indica un teléfono WhatsApp";
    else if (!isValidPhone(telefono)) next.telefono = "Usa un móvil venezolano (ej. 0412-0000000)";
    const hint = cedulaHint(cedula);
    if (hint) next.cedula = hint;
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const message = `🩺 *SOLICITUD DE ATENCIÓN MÉDICA - ÁVILA GPS*
👤 *Paciente:* ${nombre}
📞 *Teléfono:* ${telefono}
🪪 *Cédula:* ${cedula || "—"}
🏥 *Servicio:* ${servicio}
👨‍⚕️ *Especialista:* ${especialista}
📍 *Modalidad:* ${modalidad}
📅 *Fecha sugerida:* ${fecha || "—"}

Por favor, confirmar disponibilidad y atención.`;

    setWaMessage(message);
    if (!reduceMotion) {
      confetti({
        particleCount: 60,
        spread: 55,
        colors: ["#6CC24A", "#0F7A33", "#5BB2F5", "#033CA0"],
      });
    }
    const win = openWhatsApp(message);
    setSubmitted(true);
    setPopupBlocked(!win);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#0A1F4D]/70 p-4 backdrop-blur-md"
      onClick={closeModal}
      role="presentation"
    >
      <div
        className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl border border-white/80 bg-white p-6 shadow-2xl sm:p-8"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="appointment-title"
      >
        <button
          type="button"
          onClick={closeModal}
          className="absolute top-4 right-4 flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600"
          aria-label="Cerrar modal"
        >
          <X size={18} />
        </button>

        <h2 id="appointment-title" className="pr-10 text-2xl font-medium tracking-tight text-[#0A2A6B]">
          Solicitar atención
        </h2>
        <p className="mt-1 text-sm text-slate-500">Completa los datos. Enviaremos tu solicitud por WhatsApp.</p>

        {submitted ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-[#0A2A6B]">
              Gracias, {nombre}. Tu solicitud está lista para enviarse por WhatsApp al {telefono}.
            </p>
            {popupBlocked ? (
              <p className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
                El navegador bloqueó la ventana emergente. Usa el enlace para continuar.
              </p>
            ) : null}
            <a
              href={whatsAppHref(waMessage)}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-green-gradient inline-flex rounded-full px-5 py-2.5 text-xs font-medium text-white"
            >
              Abrir WhatsApp
            </a>
          </div>
        ) : (
          <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={onSubmit} noValidate>
            <label className="block text-xs font-medium sm:col-span-2">
              Servicio Requerido *
              <select
                className="input-avila mt-1"
                value={servicio}
                onChange={(e) => setServicio(e.target.value)}
                required
              >
                <option value="">Selecciona…</option>
                {APPOINTMENT_SERVICES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              {errors.servicio ? <span className="mt-1 block text-[#0F7A33]">{errors.servicio}</span> : null}
            </label>

            <div className="sm:col-span-2">
              <p className="text-xs font-medium">Modalidad de Atención</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(["En el Hogar", "En Consultorio"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setModalidad(m)}
                    className={`rounded-xl px-4 py-2 text-xs font-medium ${
                      modalidad === m
                        ? "bg-[#033CA0] text-white"
                        : "border border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <label className="block text-xs font-medium">
              Nombre del Paciente *
              <input
                className="input-avila mt-1"
                placeholder="Nombre y Apellido"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                required
              />
              {errors.nombre ? <span className="mt-1 block text-red-600">{errors.nombre}</span> : null}
            </label>

            <label className="block text-xs font-medium">
              Teléfono (WhatsApp) *
              <input
                className="input-avila mt-1"
                type="tel"
                placeholder="0412-0000000"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                required
              />
              {errors.telefono ? <span className="mt-1 block text-red-600">{errors.telefono}</span> : null}
            </label>

            <label className="block text-xs font-medium">
              Cédula de Identidad
              <input
                className="input-avila mt-1"
                placeholder="V-12.345.678"
                value={cedula}
                onChange={(e) => setCedula(e.target.value)}
              />
              {errors.cedula ? <span className="mt-1 block text-amber-700">{errors.cedula}</span> : null}
            </label>

            <label className="block text-xs font-medium">
              Fecha Preferida
              <input
                className="input-avila mt-1"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </label>

            <label className="block text-xs font-medium sm:col-span-2">
              Especialista de preferencia
              <select
                className="input-avila mt-1"
                value={especialista}
                onChange={(e) => setEspecialista(e.target.value)}
              >
                <option value="Triaje por Ávila GPS">Triaje por Ávila GPS</option>
                {DOCTORS.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name} — {d.specialty}
                  </option>
                ))}
              </select>
            </label>

            <div className="sm:col-span-2">
              <button
                type="submit"
                className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
              >
                Enviar por WhatsApp
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
