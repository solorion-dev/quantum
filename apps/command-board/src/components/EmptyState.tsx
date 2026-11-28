export default function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="border border-dashed border-[#d1d5db] rounded-xl px-3 py-6 text-center">
      <p className="text-sm font-medium text-[#6b7280]">{title}</p>
      {hint && <p className="text-xs text-[#9ca3af] mt-1">{hint}</p>}
    </div>
  );
}
