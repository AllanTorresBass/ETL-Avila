import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

function allowedEmails(): string[] {
  return (process.env.CLERK_ALLOWED_EMAILS || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

async function emailAllowed(): Promise<boolean> {
  const allow = allowedEmails();
  if (allow.length === 0) return true;
  const user = await currentUser();
  const emails = user?.emailAddresses.map((e) => e.emailAddress.toLowerCase()) ?? [];
  return emails.some((e) => allow.includes(e));
}

/** For Server Components / pages — redirects to sign-in when needed. */
export async function requireStaffPage() {
  await auth.protect();
  if (!(await emailAllowed())) {
    throw new Error("FORBIDDEN_STAFF");
  }
}

/** For Route Handlers — returns a Response when unauthorized. */
export async function requireStaffApi(): Promise<NextResponse | null> {
  const session = await auth();
  if (!session.userId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!(await emailAllowed())) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  return null;
}
