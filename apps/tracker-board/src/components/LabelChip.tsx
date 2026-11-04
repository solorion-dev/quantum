import { labelColor } from '../lib/meta'
export function LabelChip({ name }: { name: string }) {
  const c = labelColor(name)
  return <span className="tb-label">{c && <span className="tb-label-dot" aria-hidden="true" style={{ background: c }} />}{name}</span>
}
