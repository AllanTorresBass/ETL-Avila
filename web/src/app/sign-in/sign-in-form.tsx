"use client";

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { useActionState } from "react";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { signIn } from "./actions";

const FAILED = "Correo o contraseña incorrectos.";

export interface SignInFormProps {
  nextPath: string;
  initialError: boolean;
}

export function SignInForm({ nextPath, initialError }: SignInFormProps) {
  const [state, formAction, pending] = useActionState(signIn, null);
  const [email, setEmail] = useState("");
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const message = state?.error ?? (initialError ? FAILED : "");
  const attempt = state?.attempt ?? (initialError ? 0 : -1);
  const errorId = message ? "sign-in-error" : undefined;

  useEffect(() => {
    if (attempt < 0) return;
    if (email.length > 0 && passwordRef.current) {
      passwordRef.current.value = "";
      passwordRef.current.focus();
      return;
    }
    emailRef.current?.focus();
  }, [attempt, email.length]);

  function onPasswordKey(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState("CapsLock"));
  }

  return (
    <form action={formAction} className="w-full max-w-sm rise-in" aria-busy={pending} style={{ "--i": 1 } as CSSProperties}>
      <p className="text-xs font-medium tracking-wider text-info uppercase">Personal</p>
      <h1 className="mt-1 text-3xl font-medium tracking-tight">Entrar</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Lector interno de personas, facturas y documentos. El super admin crea las cuentas y asigna el rol.
      </p>
      <div className="mt-6 space-y-4">
        {nextPath ? <input type="hidden" name="next" value={nextPath} /> : null}
        <label htmlFor="email" className="block text-sm font-medium text-foreground">
          Correo
          <input
            ref={emailRef}
            id="email"
            name="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoFocus={!initialError}
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            inputMode="email"
            enterKeyHint="next"
            disabled={pending}
            aria-invalid={message ? true : undefined}
            aria-describedby={errorId}
            className="mt-1.5 block h-12 w-full rounded-xl border border-input bg-card px-4 text-sm text-foreground disabled:opacity-70"
          />
        </label>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-foreground">
            Contraseña
          </label>
          <div className="relative mt-1.5">
            <input
              ref={passwordRef}
              id="password"
              name="password"
              type={visible ? "text" : "password"}
              required
              autoComplete="current-password"
              enterKeyHint="go"
              disabled={pending}
              aria-invalid={message ? true : undefined}
              aria-describedby={[capsLock ? "sign-in-caps" : null, errorId].filter(Boolean).join(" ") || undefined}
              onKeyDown={onPasswordKey}
              onKeyUp={onPasswordKey}
              onBlur={() => setCapsLock(false)}
              className="block h-12 w-full rounded-xl border border-input bg-card px-4 pr-12 text-sm text-foreground disabled:opacity-70"
            />
            <button
              type="button"
              className="absolute inset-y-1 right-1 flex w-10 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
              aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
              aria-pressed={visible}
              disabled={pending}
              onClick={() => setVisible((value) => !value)}
            >
              {visible ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
          {capsLock ? (
            <p id="sign-in-caps" role="status" className="mt-1.5 text-xs text-warning">
              Bloq Mayús está activo.
            </p>
          ) : null}
        </div>
        {message ? (
          <p id="sign-in-error" role="alert" className="rounded-2xl bg-danger-soft px-4 py-3 text-sm text-danger">
            {message}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={pending}
          aria-busy={pending}
          className="btn-green-gradient inline-flex h-12 w-full items-center justify-center gap-2 rounded-full px-5 text-sm font-medium text-white"
        >
          {pending ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          {pending ? "Entrando…" : "Entrar"}
        </button>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        La sesión queda en este navegador. Ciérrala si compartes el equipo.
      </p>
    </form>
  );
}
