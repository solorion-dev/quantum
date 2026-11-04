// Local multi-select: Popover + kit Checkbox. Keyboard: Tab/Shift+Tab through options, Space toggles, Esc closes.
import { Checkbox } from '@dsect/ui'
import { Popover } from './Popover'

export interface Option { value: string; label: string; count?: number }
export function MultiSelect({ label, options, value, onChange }: {
  label: string; options: Option[]; value: string[]; onChange: (v: string[]) => void
}) {
  const summary = value.length === 0 ? 'Any' : value.length === 1 ? options.find((o) => o.value === value[0])?.label ?? value[0] : `${value.length} selected`
  return (
    <Popover label={`${label} filter: ${summary}`} trigger={<><span className="tb-ms-label">{label}</span><span className="tb-ms-value">{summary}</span><span aria-hidden="true">▾</span></>}>
      <fieldset className="tb-ms">
        <legend className="tb-ms-legend">{label}</legend>
        {options.map((o) => (
          <Checkbox key={o.value} checked={value.includes(o.value)}
            onChange={(e) => onChange(e.currentTarget.checked ? [...value, o.value] : value.filter((v) => v !== o.value))}
            label={<>{o.label}{o.count !== undefined && <span className="tb-count"> {o.count}</span>}</>} />
        ))}
        {value.length > 0 && <button type="button" className="btn btn-small ghost" onClick={() => onChange([])}>Clear {label.toLowerCase()}</button>}
      </fieldset>
    </Popover>
  )
}
