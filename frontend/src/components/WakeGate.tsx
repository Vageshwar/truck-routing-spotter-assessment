import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { checkHealth } from '../api'

// The backend runs on Render's free tier, which sleeps after 15 minutes
// without traffic and takes about a minute to start again. Instead of a
// blank page, explain the wait while we poll the health endpoint.

const SHOW_SCREEN_AFTER_MS = 2_000
const POLL_EVERY_MS = 3_000
const GIVE_UP_AFTER_MS = 3 * 60_000

type Status = 'checking' | 'waking' | 'ready' | 'failed'

export function WakeGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('checking')
  const [elapsed, setElapsed] = useState(0)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let done = false
    const started = Date.now()
    const controller = new AbortController()

    const screenTimer = setTimeout(() => {
      if (!done) setStatus('waking')
    }, SHOW_SCREEN_AFTER_MS)
    const clock = setInterval(() => setElapsed(Date.now() - started), 1_000)

    async function poll() {
      while (!done) {
        try {
          await checkHealth(controller.signal)
          done = true
          setStatus('ready')
          return
        } catch {
          if (controller.signal.aborted) return
          if (Date.now() - started > GIVE_UP_AFTER_MS) {
            done = true
            setStatus('failed')
            return
          }
          await new Promise((resolve) => setTimeout(resolve, POLL_EVERY_MS))
        }
      }
    }
    poll()

    return () => {
      done = true
      controller.abort()
      clearTimeout(screenTimer)
      clearInterval(clock)
    }
  }, [attempt])

  const retry = useCallback(() => {
    setStatus('checking')
    setElapsed(0)
    setAttempt((n) => n + 1)
  }, [])

  if (status === 'ready') return <>{children}</>
  if (status === 'checking') return null

  const seconds = Math.floor(elapsed / 1000)
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

  return (
    <div className="flex h-full items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        {status === 'waking' ? (
          <>
            <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-800" />
            <h1 className="text-lg font-semibold">Starting the server</h1>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              This demo runs on a free Render server that goes to sleep after 15 minutes
              without visitors. Waking it up usually takes about a minute, so please wait.
              The app opens on its own as soon as it is ready.
            </p>
            <p className="mt-5 font-mono text-sm text-slate-500" aria-live="polite">
              Waiting {clock}
            </p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold">The server is still not up</h1>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              It has been over 3 minutes. The free server may be having a slow start. Try
              again, or refresh the page in a minute.
            </p>
            <button
              type="button"
              onClick={retry}
              className="mt-5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Try again
            </button>
          </>
        )}
      </div>
    </div>
  )
}
