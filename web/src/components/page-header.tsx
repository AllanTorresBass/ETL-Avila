export function PageHeader({
  eyebrow,
  title,
  description,
  badges,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  badges?: { label: string; className?: string }[];
}) {
  return (
    <div>
      {eyebrow ? (
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">{eyebrow}</p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-medium tracking-tight">{title}</h1>
        {badges?.map((badge) => (
          <span
            key={badge.label}
            className={
              badge.className ||
              "rounded-full bg-[#033CA0]/10 px-3 py-1 text-xs font-medium text-[#033CA0]"
            }
          >
            {badge.label}
          </span>
        ))}
      </div>
      {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
    </div>
  );
}
