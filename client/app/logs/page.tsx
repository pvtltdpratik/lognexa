"use client"

import { BellRingIcon, FilterXIcon, SearchIcon } from "lucide-react"
import { useSearchParams } from "next/navigation"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { LogDetailSheet } from "@/components/log-detail-sheet"
import { Pager } from "@/components/pager"
import { RiskMeter, SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatShort, humanize } from "@/lib/format"
import {
  actionValues,
  logFiltersSchema,
  logStatusValues,
  sensitivityValues,
  severityValues,
  type LogFilters,
} from "@/lib/schemas"

const EMPTY: LogFilters = { search: "", action: "", status: "", sensitivity: "", severity: "", start: "", end: "" }
const SORTS = { timestamp_desc: "Newest first", timestamp_asc: "Oldest first", risk_desc: "Highest risk" } as const

function Select<T extends string>({ id, label, value, values, onChange, all = "All" }: {
  id: string; label: string; value: string; values: readonly T[]; onChange: (v: string) => void; all?: string
}) {
  return (
    <Field className="min-w-32 flex-1">
      <FieldLabel htmlFor={id} className="text-xs">{label}</FieldLabel>
      <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)} className="w-full">
        <NativeSelectOption value="">{all}</NativeSelectOption>
        {values.map((v) => <NativeSelectOption key={v} value={v}>{humanize(v)}</NativeSelectOption>)}
      </NativeSelect>
    </Field>
  )
}

function LogsView() {
  const params = useSearchParams()
  const [filters, setFilters] = React.useState<LogFilters>(EMPTY)
  const [userId, setUserId] = React.useState(params.get("user") ?? "")
  const [sort, setSort] = React.useState<keyof typeof SORTS>("timestamp_desc")
  const [page, setPage] = React.useState(1)
  const [selected, setSelected] = React.useState<number | null>(null)

  const parsed = logFiltersSchema.safeParse(filters)
  const fieldErrors = parsed.success ? {} : parsed.error.flatten().fieldErrors
  const search = useDebounced(filters.search ?? "", 350)

  // Only valid filters are sent to the API; invalid ones show inline errors instead.
  const query = parsed.success
    ? {
        page,
        page_size: 25,
        sort,
        search: search.trim() || undefined,
        user_id: userId || undefined,
        action: filters.action,
        status: filters.status,
        sensitivity: filters.sensitivity,
        severity: filters.severity,
        start: filters.start ? `${filters.start}T00:00:00` : undefined,
        end: filters.end ? `${filters.end}T23:59:59` : undefined,
      }
    : null
  const key = JSON.stringify(query)
  const { data, error, loading, reload } = useApi(
    () => (query ? api.logs(query) : Promise.resolve(null)),
    [key]
  )
  const users = useApi(() => api.users(), [])

  const update = (patch: Partial<LogFilters>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setPage(1)
  }
  const active = Object.values(filters).some(Boolean) || userId !== ""

  return (
    <>
      <PageIntro
        title="Access logs"
        description="Every synthetic access event with its computed risk. Select a row to see the full explanation."
      />
      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
            <Field className="lg:max-w-sm" data-invalid={!!fieldErrors.search}>
              <FieldLabel htmlFor="search" className="text-xs">Search</FieldLabel>
              <InputGroup>
                <InputGroupAddon><SearchIcon /></InputGroupAddon>
                <InputGroupInput
                  id="search"
                  placeholder="Username, IP, resource or city"
                  value={filters.search}
                  maxLength={120}
                  aria-invalid={!!fieldErrors.search}
                  onChange={(e) => update({ search: e.target.value })}
                />
              </InputGroup>
              <FieldError>{fieldErrors.search?.[0]}</FieldError>
            </Field>
            <Field className="min-w-40 flex-1">
              <FieldLabel htmlFor="user" className="text-xs">User</FieldLabel>
              <NativeSelect id="user" value={userId} onChange={(e) => { setUserId(e.target.value); setPage(1) }} className="w-full" disabled={users.loading}>
                <NativeSelectOption value="">All users</NativeSelectOption>
                {users.data?.map((u) => <NativeSelectOption key={u.id} value={String(u.id)}>{u.username}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <Field className="min-w-36 flex-1">
              <FieldLabel htmlFor="sort" className="text-xs">Sort</FieldLabel>
              <NativeSelect id="sort" value={sort} onChange={(e) => { setSort(e.target.value as keyof typeof SORTS); setPage(1) }} className="w-full">
                {Object.entries(SORTS).map(([v, l]) => <NativeSelectOption key={v} value={v}>{l}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
          </div>
          <div className="flex flex-col flex-wrap gap-4 sm:flex-row sm:items-start">
            <Select id="severity" label="Severity" value={filters.severity ?? ""} values={severityValues} onChange={(v) => update({ severity: v as LogFilters["severity"] })} />
            <Select id="action" label="Action" value={filters.action ?? ""} values={actionValues} onChange={(v) => update({ action: v as LogFilters["action"] })} />
            <Select id="status" label="Status" value={filters.status ?? ""} values={logStatusValues} onChange={(v) => update({ status: v as LogFilters["status"] })} />
            <Select id="sensitivity" label="Sensitivity" value={filters.sensitivity ?? ""} values={sensitivityValues} onChange={(v) => update({ sensitivity: v as LogFilters["sensitivity"] })} />
            <Field className="min-w-36 flex-1">
              <FieldLabel htmlFor="start" className="text-xs">From</FieldLabel>
              <Input id="start" type="date" value={filters.start} onChange={(e) => update({ start: e.target.value })} />
            </Field>
            <Field className="min-w-36 flex-1" data-invalid={!!fieldErrors.end}>
              <FieldLabel htmlFor="end" className="text-xs">To</FieldLabel>
              <Input id="end" type="date" value={filters.end} aria-invalid={!!fieldErrors.end} onChange={(e) => update({ end: e.target.value })} />
              <FieldError>{fieldErrors.end?.[0]}</FieldError>
            </Field>
            <Button variant="ghost" size="sm" className="self-end" disabled={!active} onClick={() => { setFilters(EMPTY); setUserId(""); setPage(1) }}>
              <FilterXIcon data-icon="inline-start" /> Clear
            </Button>
          </div>
        </CardContent>
      </Card>

      {!!error && <ErrorState error={error} onRetry={reload} />}
      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          {loading && !data ? (
            <TableSkeleton rows={10} cols={6} />
          ) : data && data.total === 0 ? (
            <EmptyState title="No matching events" description="Try removing some filters or widening the date range." />
          ) : data ? (
            <>
              <Table className={loading ? "opacity-60 transition-opacity" : ""}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>User</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead className="hidden md:table-cell">Resource</TableHead>
                    <TableHead className="hidden lg:table-cell">Source IP</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead>Severity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((log) => (
                    <TableRow
                      key={log.id}
                      className="cursor-pointer"
                      tabIndex={0}
                      onClick={() => setSelected(log.id)}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setSelected(log.id)}
                      aria-label={`Open event ${log.id}`}
                    >
                      <TableCell className="font-mono text-xs whitespace-nowrap">{formatShort(log.timestamp)}</TableCell>
                      <TableCell className="font-medium">{log.username}</TableCell>
                      <TableCell>
                        <span className="capitalize">{humanize(log.action)}</span>
                        {log.status !== "success" && <span className="ml-1.5 text-xs text-destructive">{log.status}</span>}
                      </TableCell>
                      <TableCell className="hidden max-w-56 truncate font-mono text-xs md:table-cell">{log.resource}</TableCell>
                      <TableCell className="hidden font-mono text-xs lg:table-cell">{log.ip_address} <span className="text-muted-foreground">{log.country}</span></TableCell>
                      <TableCell><RiskMeter score={log.risk_score} severity={log.severity} /></TableCell>
                      <TableCell>
                        <span className="flex items-center gap-2">
                          <SeverityBadge severity={log.severity} />
                          {log.has_alert && <BellRingIcon className="size-3.5 text-primary" aria-label="Has alert" />}
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
      <LogDetailSheet logId={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </>
  )
}

export default function LogsPage() {
  return (
    <React.Suspense fallback={<TableSkeleton rows={10} cols={6} />}>
      <LogsView />
    </React.Suspense>
  )
}
