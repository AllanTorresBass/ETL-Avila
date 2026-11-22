"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { requirePermission } from "@/lib/auth";
import { linkAuthorizationToInvoice, unlinkAuthorization } from "@/lib/authorization-data";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function linkAuthorization(formData: FormData): Promise<void> {
  const reviewer = (await requirePermission("review")).email;
  const id = String(formData.get("id") || "");
  const invoiceId = String(formData.get("invoice_id") || "");
  if (!UUID.test(id) || !UUID.test(invoiceId)) throw new Error("BAD_REQUEST");
  const result = await linkAuthorizationToInvoice(reviewer, id, invoiceId);
  if (result !== "done") redirect(`/autorizaciones/${id}?aviso=${result}`);
  refresh();
}

export async function unlinkAuthorizationAction(formData: FormData): Promise<void> {
  const reviewer = (await requirePermission("review")).email;
  const id = String(formData.get("id") || "");
  if (!UUID.test(id)) throw new Error("BAD_REQUEST");
  const result = await unlinkAuthorization(reviewer, id);
  if (result !== "done") redirect(`/autorizaciones/${id}?aviso=${result}`);
  refresh();
}
