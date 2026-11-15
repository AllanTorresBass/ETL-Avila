import { MessageCircle } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { whatsAppHref } from "../lib/whatsapp";

const PRESET =
  "Hola Ávila GPS, me gustaría recibir información sobre atención médica integral.";

export function WhatsAppFab() {
  const reduceMotion = useReducedMotion();

  return (
    <motion.a
      href={whatsAppHref(PRESET)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Abrir WhatsApp"
      className="fixed right-6 bottom-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-[#6CC24A] text-white shadow-lg"
      initial={reduceMotion ? false : { opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: reduceMotion ? 0 : 1, duration: 0.4 }}
    >
      {!reduceMotion ? (
        <span className="absolute inset-0 animate-ping rounded-full bg-[#6CC24A]/40" aria-hidden />
      ) : null}
      <MessageCircle className="relative h-6 w-6" />
    </motion.a>
  );
}
