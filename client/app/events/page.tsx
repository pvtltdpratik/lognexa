"use client"

import { format } from "date-fns"
import { BellRingIcon, ClockIcon, PlayIcon, SearchIcon } from "lucide-react"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { useAuth } from "@/components/auth"
import { EndpointEventSheet } from "@/components/endpoint-event-sheet"
import { OsBadge } from "@/components/endpoint-badges"
import { Pager } from "@/components/pager"
import { SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, SignInRequired, TableSkeleton } from "@/components/states"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatPrecise, humanize } from "@/lib/format"

const CATEGORIES = ["authentication", "process", "network", "file", "persistence", "system"]

type Sort = "newest" | "oldest" | "risk_desc"
const SORTS: { value: Sort; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "risk_desc", label: "Highest risk" },
]

type Range = "all" | "15m" | "1h" | "6h" | "24h" | "7d" | "custom"
const MIN = 60_000
const RANGES: { value: Range; label: string; ms?: number }[] = [
  { value: "all", label: "Any time" },
  { value: "15m", label: "Last 15 minutes", ms: 15 * MIN },
  { value: "1h", label: "Last hour", ms: 60 * MIN },
  { value: "6h", label: "Last 6 hours", ms: 6 * 60 * MIN },
  { value: "24h", label: "Last 24 hours", ms: 24 * 60 * MIN },
  { value: "7d", label: "Last 7 days", ms: 7 * 24 * 60 * MIN },
  { value: "custom", label: "Custom range…" },
]

/** Time bounds for the API, as UTC ISO strings. Relative ranges are recomputed on each call. */
function timeBounds(range: Range, from: string, to: string): { start?: string; end?: string } {
  if (range === "custom") {
    return {
      // datetime-local values are local wall-clock time; toISOString() converts to UTC.
      start: from ? new Date(from).toISOString() : undefined,
      // "To" is minute-precise; include the whole minute the user picked.
      end: to ? new Date(new Date(to).getTime() + MIN - 1).toISOString() : undefined,
    }
  }
  const ms = RANGES.find((r) => r.value === range)?.ms
  return ms ? { start: new Date(Date.now() - ms).toISOString() } : {}
}

function describeRange(range: Range, from: string, to: string): string {
  if (range !== "custom") return RANGES.find((r) => r.value === range)!.label.toLowerCase()
  const fmt = (v: string) => format(new Date(v), "dd MMM yyyy, HH:mm")
  if (from && to) return `from ${fmt(from)} to ${fmt(to)}`
  if (from) return `since ${fmt(from)}`
  if (to) return `up to ${fmt(to)}`
  return "any time"
}

export default function EventsPage() {
  const { signedIn, ready } = useAuth()
  const [os, setOs] = React.useState("")
  const [category, setCategory] = React.useState("")
  const [severity, setSeverity] = React.useState("")
  const [flagged, setFlagged] = React.useState(false)
  const [searchInput, setSearchInput] = React.useState("")
  const [sort, setSort] = React.useState<Sort>("newest")
  const [range, setRange] = React.useState<Range>("all")
  const [from, setFrom] = React.useState("")
  const [to, setTo] = React.useState("")
  const [page, setPage] = React.useState(1)
  const [live, setLive] = React.useState(false)
  const [tick, setTick] = React.useState(0)
  const [selected, setSelected] = React.useState<number | null>(null)
  const search = useDebounced(searchInput.trim(), 300)

  const rangeError = range === "custom" && from && to && new Date(to) < new Date(from)
    ? "“To” must be the same as or later than “From”" : null
  // New arrivals only appear at the top of a newest-first view over a moving window.
  const liveAllowed = sort === "newest" && range !== "custom"
  const liveOn = live && liveAllowed

  // Live mode polls the newest page every 5s (only on page 1).
  React.useEffect(() => {
    if (!liveOn) return
    const id = setInterval(() => setTick((t) => t + 1), 5000)
    return () => clearInterval(id)
  }, [liveOn])

  const reset = () => setPage(1)
  const { data, error, loading, reload } = useApi(
    () => (signedIn && !rangeError ? api.endpointEvents({
      page, page_size: 50, sort, os_type: os, category, severity,
      flagged: flagged || undefined, search: search || undefined,
      ...timeBounds(range, from, to),
    }) : Promise.resolve(null)),
    [signedIn, page, sort, os, category, severity, flagged, search, range, from, to, rangeError, tick]
  )

  if (ready && !signedIn) {
    return (
      <>
        <PageIntro title="Live events" description="Telemetry streaming in from enrolled endpoints." />
        <SignInRequired feature="Endpoint telemetry" />
      </>
    )
  }

  const sortLabel = SORTS.find((s) => s.value === sort)!.label.toLowerCase()
  return (
    <>
      <PageIntro
        title="Live events"
        description="Normalised Windows and Linux telemetry. Flagged events triggered at least one detection rule."
        actions={
          <label className="flex items-center gap-2 text-sm" title={liveAllowed ? undefined : "Live updates need “Newest first” and a non-custom time range"}>
            <Switch checked={liveOn} disabled={!liveAllowed} onCheckedChange={(v) => { setLive(v); setPage(1) }} id="live" />
            <span className="flex items-center gap-1"><PlayIcon className="size-3.5" /> Live</span>
            {!liveAllowed && <span className="text-xs text-muted-foreground">(newest first only)</span>}
          </label>
        }
      />
      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col flex-wrap gap-4 sm:flex-row sm:items-end">
            <Field className="sm:max-w-xs">
              <FieldLabel htmlFor="ev-search" className="text-xs">Search</FieldLabel>
              <InputGroup>
                <InputGroupAddon><SearchIcon /></InputGroupAddon>
                <InputGroupInput id="ev-search" placeholder="User, process, IP, file, host" value={searchInput} maxLength={100}
                  onChange={(e) => { setSearchInput(e.target.value); reset() }} />
              </InputGroup>
            </Field>
            <Field className="min-w-32 flex-1"><FieldLabel htmlFor="ev-os" className="text-xs">OS</FieldLabel>
              <NativeSelect id="ev-os" value={os} onChange={(e) => { setOs(e.target.value); reset() }} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption><NativeSelectOption value="windows">Windows</NativeSelectOption><NativeSelectOption value="linux">Linux</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Field className="min-w-32 flex-1"><FieldLabel htmlFor="ev-cat" className="text-xs">Category</FieldLabel>
              <NativeSelect id="ev-cat" value={category} onChange={(e) => { setCategory(e.target.value); reset() }} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption>
                {CATEGORIES.map((c) => <NativeSelectOption key={c} value={c}>{humanize(c)}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <Field className="min-w-32 flex-1"><FieldLabel htmlFor="ev-sev" className="text-xs">Severity</FieldLabel>
              <NativeSelect id="ev-sev" value={severity} onChange={(e) => { setSeverity(e.target.value); reset() }} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption>
                {["low", "medium", "high", "critical"].map((s) => <NativeSelectOption key={s} value={s}>{humanize(s)}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <Switch checked={flagged} onCheckedChange={(v) => { setFlagged(v); reset() }} /> Flagged only
            </label>
          </div>

          <div className="flex flex-col flex-wrap gap-4 border-t pt-4 sm:flex-row sm:items-start">
            <Field className="min-w-40 sm:w-44"><FieldLabel htmlFor="ev-sort" className="text-xs">Order</FieldLabel>
              <NativeSelect id="ev-sort" value={sort} onChange={(e) => { setSort(e.target.value as Sort); reset() }} className="w-full">
                {SORTS.map((s) => <NativeSelectOption key={s.value} value={s.value}>{s.label}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <Field className="min-w-40 sm:w-48"><FieldLabel htmlFor="ev-range" className="text-xs">Time range</FieldLabel>
              <NativeSelect id="ev-range" value={range} onChange={(e) => { setRange(e.target.value as Range); reset() }} className="w-full">
                {RANGES.map((r) => <NativeSelectOption key={r.value} value={r.value}>{r.label}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            {range === "custom" && (
              <>
                <Field className="sm:w-56"><FieldLabel htmlFor="ev-from" className="text-xs">From (local time)</FieldLabel>
                  <Input id="ev-from" type="datetime-local" value={from} max={to || undefined}
                    onChange={(e) => { setFrom(e.target.value); reset() }} />
                </Field>
                <Field className="sm:w-56" data-invalid={!!rangeError}><FieldLabel htmlFor="ev-to" className="text-xs">To (local time)</FieldLabel>
                  <Input id="ev-to" type="datetime-local" value={to} min={from || undefined} aria-invalid={!!rangeError}
                    onChange={(e) => { setTo(e.target.value); reset() }} />
                  <FieldError>{rangeError}</FieldError>
                </Field>
              </>
            )}
          </div>

          {!rangeError && data && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground" aria-live="polite">
              <ClockIcon className="size-3.5" />
              {data.total.toLocaleString()} event{data.total === 1 ? "" : "s"} · {describeRange(range, from, to)} · {sortLabel}
              {liveOn && " · updating every 5s"}
            </p>
          )}

          {rangeError ? (
            <EmptyState title="Fix the time range" description="Choose a “To” time that is the same as or later than “From”." />
          ) : error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? (
            <TableSkeleton rows={10} cols={6} />
          ) : data && data.total === 0 ? (
            <EmptyState title="No events" description="No telemetry matches these filters and time range." />
          ) : data ? (
            <>
              <Table className={loading ? "opacity-60" : ""}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Host</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead className="hidden md:table-cell">Detail</TableHead>
                    <TableHead className="hidden sm:table-cell">Rules</TableHead>
                    <TableHead>Severity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((e) => (
                    <TableRow key={e.id} className="cursor-pointer" tabIndex={0} onClick={() => setSelected(e.id)}
                      onKeyDown={(k) => k.key === "Enter" && setSelected(e.id)}>
                      <TableCell className="font-mono text-xs whitespace-nowrap">{formatPrecise(e.timestamp)}</TableCell>
                      <TableCell><div className="font-medium">{e.hostname}</div><OsBadge os={e.os_type} /></TableCell>
                      <TableCell><span className="capitalize">{humanize(e.event_type)}</span><div className="text-xs text-muted-foreground">{humanize(e.category)}</div></TableCell>
                      <TableCell className="hidden max-w-64 truncate font-mono text-xs md:table-cell">
                        {e.command_line || e.file_path || (e.dst_ip ? `${e.dst_ip}:${e.dst_port ?? ""}` : "") || e.process_name || e.username || ""}
                      </TableCell>
                      <TableCell className="hidden font-mono text-xs text-primary sm:table-cell">{e.rule_codes.join(" ") || "—"}</TableCell>
                      <TableCell>
                        <span className="flex items-center gap-1.5">
                          <SeverityBadge severity={e.severity} />
                          {e.alert_id && <BellRingIcon className="size-3.5 text-primary" aria-label="Has alert" />}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pager page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
            </>
          ) : null}
        </CardContent>
      </Card>
      <EndpointEventSheet eventId={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </>
  )
}
