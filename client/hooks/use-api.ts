"use client"

import * as React from "react"

interface Settled<T> {
  key: string
  data: T | null
  error: unknown
}

/**
 * Minimal data-fetching hook: re-runs ``fetcher`` whenever ``deps`` change,
 * ignores stale responses and exposes ``reload`` for retry buttons.
 *
 * ``loading`` is derived (the last settled request key differs from the
 * current one) instead of being set inside the effect, and the previous data
 * is kept while a new request is in flight so tables don't flash empty.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: React.DependencyList) {
  const [tick, setTick] = React.useState(0)
  const [settled, setSettled] = React.useState<Settled<T>>({ key: "", data: null, error: null })
  const key = `${JSON.stringify(deps)}#${tick}`
  const load = React.useEffectEvent(fetcher)

  React.useEffect(() => {
    let active = true
    load()
      .then((data) => active && setSettled({ key, data, error: null }))
      .catch((error) => active && setSettled((s) => ({ key, data: s.data, error })))
    return () => {
      active = false
    }
  }, [key])

  const reload = React.useCallback(() => setTick((t) => t + 1), [])
  const loading = settled.key !== key
  return { data: settled.data, error: loading ? null : settled.error, loading, reload }
}

export function useDebounced<T>(value: T, delay = 300) {
  const [v, setV] = React.useState(value)
  React.useEffect(() => {
    const id = setTimeout(() => setV(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return v
}
