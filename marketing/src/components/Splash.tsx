import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

const SPLASH_KEY = "avilaSplashSeen";

export function Splash() {
  const reduceMotion = useReducedMotion();
  const [visible, setVisible] = useState(() => {
    try {
      return sessionStorage.getItem(SPLASH_KEY) !== "1";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    if (!visible) return;
    const hold = reduceMotion ? 400 : 2200;
    const fade = reduceMotion ? 100 : 800;
    const t = window.setTimeout(() => {
      setVisible(false);
      try {
        sessionStorage.setItem(SPLASH_KEY, "1");
      } catch {
        /* ignore */
      }
    }, hold + fade);
    return () => window.clearTimeout(t);
  }, [visible, reduceMotion]);

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#0A1F4D] text-white"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduceMotion ? 0.1 : 0.8, ease: [0.76, 0, 0.24, 1] }}
        >
          <p className="text-sm font-light tracking-wide">Cargando tu bienestar…</p>
          <svg className="mt-6 h-8 w-40 text-[#5BB2F5]" viewBox="0 0 160 32" fill="none" aria-hidden>
            <path
              d="M0 16 H28 L36 8 L44 24 L52 12 L60 16 H160"
              stroke="currentColor"
              strokeWidth="2"
              className={reduceMotion ? "" : "animate-pulse"}
            />
          </svg>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
