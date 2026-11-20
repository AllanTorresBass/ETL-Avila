"use client";

import { DashboardTabs, type DashboardTabPanel } from "@/components/dashboard-tabs";

/** @deprecated Prefer DashboardTabs — kept so existing imports keep working. */
export type EtlDetailPanel = DashboardTabPanel;

/** Switches inventory panels inside a dashboard. */
export function EtlDetailTabs({ panels }: { panels: EtlDetailPanel[] }) {
  return <DashboardTabs panels={panels} ariaLabel="Detalle operativo" />;
}
