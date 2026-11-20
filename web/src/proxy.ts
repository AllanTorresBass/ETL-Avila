import { NextResponse, type NextRequest } from "next/server";
import { neon } from "@neondatabase/serverless";
import { canAccessPath } from "@/lib/access";
import { ensureEnv } from "@/lib/env";
import { userFromTokenHash } from "@/lib/session-db";
import { hashSessionToken, SESSION_COOKIE } from "@/lib/session-token";

function isPublic(pathname: string) {
  return pathname === "/sign-in" || pathname.startsWith("/sign-in/");
}

function isApi(pathname: string) {
  return pathname.startsWith("/api/");
}

function apiStatus(status: 401 | 403 | 503) {
  const error = status === 401 ? "unauthorized" : status === 403 ? "forbidden" : "unavailable";
  return NextResponse.json({ error }, { status });
}

function redirectToSignIn(request: NextRequest) {
  if (isApi(request.nextUrl.pathname)) return apiStatus(401);
  const url = request.nextUrl.clone();
  url.pathname = "/sign-in";
  url.search = "";
  const next = request.nextUrl.pathname;
  if (next !== "/" && next !== "/sign-in") {
    url.searchParams.set("next", next);
  }
  return NextResponse.redirect(url);
}

function denyForbidden(request: NextRequest) {
  if (isApi(request.nextUrl.pathname)) return apiStatus(403);
  const url = request.nextUrl.clone();
  url.pathname = "/forbidden";
  url.search = "";
  return NextResponse.redirect(url);
}

export default async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/sign-up" || pathname.startsWith("/sign-up/")) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.search = "";
    return NextResponse.redirect(url);
  }
  if (isPublic(pathname)) return NextResponse.next();

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return redirectToSignIn(request);

  ensureEnv();
  const dbUrl = process.env.DATABASE_URL || process.env.DATABASE_URL_UNPOOLED;
  if (!dbUrl) return redirectToSignIn(request);

  try {
    const db = neon(dbUrl);
    const user = await userFromTokenHash(db, await hashSessionToken(token));
    if (!user) return redirectToSignIn(request);
    if (!canAccessPath(user.role, pathname)) return denyForbidden(request);
    return NextResponse.next();
  } catch {
    if (isApi(pathname)) return apiStatus(503);
    return new NextResponse("No se pudo comprobar la sesión.", { status: 503 });
  }
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
