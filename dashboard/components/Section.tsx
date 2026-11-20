export default function Section({
  title,
  meta,
  children,
  className = "",
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      <div className="mb-3 flex items-baseline justify-between border-b border-slate-800 pb-2">
        <h2 className="text-xs text-slate-400">{title}</h2>
        {meta && <span className="text-xs text-slate-600">{meta}</span>}
      </div>
      {children}
    </section>
  );
}