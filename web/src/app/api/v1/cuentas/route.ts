import { NextResponse } from "next/server";
import { listAccounts, listInvoiceMonths, listInvoiceYears } from "@/lib/account-data";
import { isApiDenial, requireApiPermission } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const [accounts, years, months] = await Promise.all([
    listAccounts(),
    listInvoiceYears(),
    listInvoiceMonths(),
  ]);
  return NextResponse.json({ accounts, years, months });
}
