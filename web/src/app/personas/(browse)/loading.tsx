import { PersonasFilterSkeleton, PersonasListSkeleton } from "@/components/personas-page-skeleton";

/** Soft-nav within the list: keep header/KPIs, skeleton filters + rows. */
export default function PersonasBrowseLoading() {
  return (
    <div className="space-y-6">
      <PersonasFilterSkeleton />
      <PersonasListSkeleton />
    </div>
  );
}
