"use client"

import { BellRingIcon, PlayIcon, SearchIcon } from "lucide-react"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { useAuth } from "@/components/auth"
import { EndpointEventSheet } from "@/components/endpoint-event-sheet"
import { OsBadge } from "@/components/endpoint-badges"
import { Pager } from "@/components/pager"
import { SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, SignInRequired, TableSkeleton } from "@/components/states"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatShort, humanize } from "@/lib/format"

const CATEGORIES = ["authentication", "process", "network", "file", "persistence", "system"]

export default function EventsPage() {
  const { signedIn, ready } = useAuth()
  const [os, setOs] = React.useState("")
  const [category, setCategory] = React.useState("")
  const [severity, setSeverity] = React.useState("")
  const [flagged, setFlagged] = React.useState(false)
  const [searchInput, setSearchInput] = React.useState("")
  const [page, setPage] = React.useState(1)
  const [live, setLive] = React.useState(false)
  const [tick, setTick] = React.useState(0)
  const [selected, setSelected] = React.useState<number | null>(null)
  const search = useDebounced(searchInput.trim(), 300)

  // Live mode polls the newest page every 5s (only on page 1).
  React.useEffect(() => {
    if (!live) return
    const id = setInterval(() => setTick((t) => t + 1), 5000)
    return () => clearInterval(id)
  }, [live])

  const reset = () => setPage(1)
  const { data, error, loading, reload } = useApi(
    () => (signedIn ? api.endpointEvents({
      page, page_size: 50, sort: "newest", os_type: os, category, severity,
      flagged: flagged || undefined, search: search || undefined,
    }) : Promise.resolve(null)),
    [signedIn, page, os, category, severity, flagged, search, tick]
  )

  if (ready && !signedIn) {
    return (
      <>
        <PageIntro title="Live events" description="Telemetry streaming in from enrolled endpoints." />
        <SignInRequired feature="Endpoint telemetry" />
      </>
    )
  }

  return (
    <>
      <PageIntro
        title="Live events"
        description="Normalised Windows and Linux telemetry. Flagged events triggered at least one detection rule."
        actions={
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={live} onCheckedChange={(v) => { setLive(v); setPage(1) }} id="live" />
            <span className="flex items-center gap-1"><PlayIcon className="size-3.5" /> Live</span>
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

          {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? (
            <TableSkeleton rows={10} cols={6} />
          ) : data && data.total === 0 ? (
            <EmptyState title="No events" description="No telemetry matches these filters yet." />
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
                      <TableCell className="font-mono text-xs whitespace-nowrap">{formatShort(e.timestamp)}</TableCell>
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
