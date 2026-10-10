import { useQuery } from '@tanstack/react-query'
import { useEffect, useId, useState } from 'react'
import { searchPlaces, type Place } from '../api'

const DEBOUNCE_MS = 300
const MIN_CHARS = 3

type Props = {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
}

export function PlaceInput({ label, placeholder, value, onChange }: Props) {
  const id = useId()
  const [text, setText] = useState(value?.label ?? '')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  // Show the place's name when the parent picks one (e.g. an example trip).
  // Clearing the place while typing must not clear what was typed.
  const [shownValue, setShownValue] = useState(value)
  if (value !== shownValue) {
    setShownValue(value)
    if (value) setText(value.label)
  }

  // Only search once the user stops typing for a moment.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [text])

  const searching = open && query.length >= MIN_CHARS && query !== value?.label
  const { data: results = [], isFetching, isError } = useQuery({
    queryKey: ['places', query],
    queryFn: ({ signal }) => searchPlaces(query, signal),
    enabled: searching,
    staleTime: 60 * 60_000,
  })

  function choose(place: Place) {
    onChange(place)
    setText(place.label)
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const showList = searching && (results.length > 0 || isFetching || isError)

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">
        {label}
      </label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        role="combobox"
        aria-expanded={showList}
        aria-controls={`${id}-list`}
        placeholder={placeholder}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setActive(0)
          setOpen(true)
          if (value) onChange(null)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
      />
      {showList && (
        <ul
          id={`${id}-list`}
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {isFetching && results.length === 0 && (
            <li className="px-3 py-2 text-slate-500">Searching…</li>
          )}
          {isError && <li className="px-3 py-2 text-red-600">Place search is not working right now.</li>}
          {results.map((place, i) => (
            <li
              key={`${place.lat},${place.lon},${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(event) => {
                event.preventDefault()
                choose(place)
              }}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-slate-100' : ''}`}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
