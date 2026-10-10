import { LEVEL_COLOR, LEVEL_LABEL, LEVELS } from '../format'

export function Legend() {
  return (
    <div className="rounded-lg bg-white/95 px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-medium text-slate-600">Weather risk</div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: LEVEL_COLOR[level] }} />
            {LEVEL_LABEL[level]}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="h-1 w-4 rounded bg-slate-400" />
          Other routes
        </li>
      </ul>
    </div>
  )
}
