import { NextResponse } from "next/server";

export const API_UUID = /^[0-9a-f-]{36}$/i;
export const LIST_PAGE_SIZE = 48;

export function requestedPage(raw: string | null): number {
  const n = Number.parseInt(raw || "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

export function textField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function notFound() {
  return NextResponse.json({ error: "not_found" }, { status: 404 });
}

export function badRequest(error: string) {
  return NextResponse.json({ error }, { status: 400 });
}
