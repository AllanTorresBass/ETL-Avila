export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
}) {
  return (
    <div>
      {eyebrow ? (
        <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">{eyebrow}</p>
      ) : null}
      <h1 className="text-3xl font-medium tracking-tight">{title}</h1>
      {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
    </div>
  );
}
