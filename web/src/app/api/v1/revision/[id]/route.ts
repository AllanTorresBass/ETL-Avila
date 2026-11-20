import { NextResponse } from "next/server";
import { API_UUID, badRequest, isRecord, notFound, readJson, textField } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { resolveReviewDecision } from "@/lib/review-resolve";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const gate = await requireApiPermission("review");
  if (isApiDenial(gate)) return gate;

  const { id } = await context.params;
  const body = await readJson(request);
  const decision = isRecord(body) ? textField(body.decision) : "";
  if (!API_UUID.test(id) || (decision !== "accept" && decision !== "reject")) {
    return badRequest("datos");
  }

  try {
    const result = await resolveReviewDecision(gate.email, id, decision);
    if (result === "missing") return notFound();
    return NextResponse.json({ ok: true });
  } catch (error) {
    const code = error instanceof Error ? error.message : "";
    if (code === "PERSON_MISSING" || code === "CI_CONFLICT") {
      return NextResponse.json({ error: code }, { status: 409 });
    }
    throw error;
  }
}
