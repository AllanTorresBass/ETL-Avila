import confetti from "canvas-confetti";
import { ChevronDown } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useReducedMotion } from "framer-motion";
import { CONTACT_INFO, CONTACT_REQUIREMENTS, WA_URL } from "../data/content";
import { isValidPhone, openWhatsApp, whatsAppHref } from "../lib/whatsapp";

export function ContactoPage() {
  const reduceMotion = useReducedMotion();
  const [nombre, setNombre] = useState("");
  const [telefono, setTelefono] = useState("");
  const [email, setEmail] = useState("");
  const [tipo, setTipo] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [waMessage, setWaMessage] = useState("");
  const [popupBlocked, setPopupBlocked] = useState(false);
  const [openAcc, setOpenAcc] = useState<"titular" | "benef" | null>("titular");

  function validate() {
    const next: Record<string, string> = {};
    if (!nombre.trim()) next.nombre = "Indica tu nombre";
    if (!telefono.trim()) next.telefono = "Indica un teléfono";
    else if (!isValidPhone(telefono)) next.telefono = "Usa un móvil venezolano (ej. 0412-1234567)";
    if (!mensaje.trim()) next.mensaje = "Escribe tu mensaje";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const message = `📩 *CONSULTA WEB - ÁVILA GPS*
👤 *Nombre:* ${nombre}
📞 *Teléfono:* ${telefono}
✉️ *Correo:* ${email || "—"}
🏥 *Requerimiento:* ${tipo || "—"}
💬 *Mensaje:* ${mensaje}

Enviado desde el formulario de contacto web.`;

    setWaMessage(message);
    if (!reduceMotion) {
      confetti({
        particleCount: 50,
        spread: 50,
        colors: ["#6CC24A", "#0F7A33", "#5BB2F5", "#033CA0"],
      });
    }
    const win = openWhatsApp(message);
    setDone(true);
    setPopupBlocked(!win);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-12 px-4 pt-28 pb-16 sm:px-6">
      <div>
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">Contacto</p>
        <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-5xl">
          Estamos a tu disposición en Valera y en todo el país
        </h1>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm sm:p-8">
          {done ? (
            <div className="space-y-4">
              <p className="text-sm text-[#0A2A6B]">
                Gracias, {nombre}. Hemos recibido tu mensaje. Nos comunicaremos contigo al {telefono} en
                la brevedad posible.
              </p>
              {popupBlocked ? (
                <p className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
                  El navegador bloqueó la ventana emergente. Usa el enlace para completar el envío por
                  WhatsApp.
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
            <form className="space-y-4" onSubmit={onSubmit} noValidate>
              <label className="block text-xs font-medium">
                Nombre y Apellido *
                <input
                  className="input-avila mt-1"
                  placeholder="Ej: Juan Pérez"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  required
                />
                {errors.nombre ? <span className="mt-1 block text-red-600">{errors.nombre}</span> : null}
              </label>
              <label className="block text-xs font-medium">
                Teléfono de Contacto *
                <input
                  className="input-avila mt-1"
                  type="tel"
                  placeholder="0412-1234567"
                  value={telefono}
                  onChange={(e) => setTelefono(e.target.value)}
                  required
                />
                {errors.telefono ? <span className="mt-1 block text-red-600">{errors.telefono}</span> : null}
              </label>
              <label className="block text-xs font-medium">
                Correo Electrónico
                <input
                  className="input-avila mt-1"
                  type="email"
                  placeholder="ejemplo@correo.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label className="block text-xs font-medium">
                Tipo de Requerimiento
                <select className="input-avila mt-1" value={tipo} onChange={(e) => setTipo(e.target.value)}>
                  <option value="">Selecciona…</option>
                  {CONTACT_REQUIREMENTS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium">
                Mensaje o Consulta *
                <textarea
                  className="input-avila mt-1 min-h-24"
                  rows={4}
                  placeholder="Escribe tu consulta o requerimiento específico..."
                  value={mensaje}
                  onChange={(e) => setMensaje(e.target.value)}
                  required
                />
                {errors.mensaje ? <span className="mt-1 block text-red-600">{errors.mensaje}</span> : null}
              </label>
              <button
                type="submit"
                className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
              >
                Enviar consulta
              </button>
            </form>
          )}
        </div>

        <div className="space-y-4">
          <article className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-medium">Sede y contacto</h2>
            <ul className="mt-4 space-y-2 text-sm text-slate-600">
              <li>{CONTACT_INFO.address}</li>
              <li>{CONTACT_INFO.hours}</li>
              <li>{CONTACT_INFO.phones}</li>
              <li>
                <a href={`mailto:${CONTACT_INFO.email}`} className="text-[#033CA0]">
                  {CONTACT_INFO.email}
                </a>
              </li>
              <li>
                <a href={WA_URL} target="_blank" rel="noopener noreferrer" className="text-[#033CA0]">
                  WhatsApp directo
                </a>
              </li>
            </ul>
          </article>
          <div className="overflow-hidden rounded-3xl border border-slate-100 shadow-sm">
            <iframe
              title="Mapa C.C. Las Acacias Valera"
              className="h-56 w-full"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              src="https://maps.google.com/maps?q=C.C.%20Las%20Acacias%20Valera&t=&z=15&ie=UTF8&iwloc=&output=embed"
            />
          </div>
        </div>
      </div>

      <section className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-medium">Documentos a traer</h2>
        <p className="mt-1 text-xs text-slate-500">Lista informativa. No se suben archivos en este sitio.</p>
        <div className="mt-4 space-y-2">
          {(
            [
              {
                key: "titular" as const,
                title: "Titular",
                body: "Cédula del titular, carnet laboral del titular, constancia de trabajo vigente (no mayor a 3 meses).",
              },
              {
                key: "benef" as const,
                title: "Beneficiarios",
                body: "Los documentos del titular, más partida de nacimiento (hijos o menores) o la cédula del beneficiario.",
              },
            ] as const
          ).map((item) => (
            <div key={item.key} className="rounded-2xl border border-slate-100">
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium"
                onClick={() => setOpenAcc((v) => (v === item.key ? null : item.key))}
                aria-expanded={openAcc === item.key}
              >
                {item.title}
                <ChevronDown
                  size={16}
                  className={`transition ${openAcc === item.key ? "rotate-180" : ""}`}
                />
              </button>
              {openAcc === item.key ? (
                <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-600">{item.body}</p>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
