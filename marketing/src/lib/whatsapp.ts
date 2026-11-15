import { WA_URL } from "../data/content";

export function openWhatsApp(message: string): Window | null {
  return window.open(
    `${WA_URL}?text=${encodeURIComponent(message)}`,
    "_blank",
    "noopener,noreferrer",
  );
}

export function whatsAppHref(message: string): string {
  return `${WA_URL}?text=${encodeURIComponent(message)}`;
}

/** Light Venezuelan mobile check: 04xx… or +58 4xx… */
export function isValidPhone(phone: string): boolean {
  const digits = phone.replace(/\D/g, "");
  if (digits.startsWith("58") && digits.length === 12) return digits[2] === "4";
  if (digits.startsWith("0") && digits.length === 11) return digits[1] === "4";
  return digits.length >= 10 && digits.length <= 12;
}

export function cedulaHint(value: string): string | null {
  if (!value.trim()) return null;
  if (!/^[VEJPvejP]-?\d{5,9}$/.test(value.trim().replace(/\./g, ""))) {
    return "Formato sugerido: V-12.345.678";
  }
  return null;
}
