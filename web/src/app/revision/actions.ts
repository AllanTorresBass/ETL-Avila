"use server";

import { refresh } from "next/cache";
import { requirePermission } from "@/lib/auth";
import { resolveReviewDecision } from "@/lib/review-resolve";

export async function resolveReview(formData: FormData): Promise<void> {
  const reviewer = (await requirePermission("review")).email;
  const id = String(formData.get("id") || "");
  const decision = String(formData.get("decision") || "");
  if (!/^[0-9a-f-]{36}$/i.test(id) || (decision !== "accept" && decision !== "reject")) {
    throw new Error("BAD_REQUEST");
  }
  await resolveReviewDecision(reviewer, id, decision);
  refresh();
}
