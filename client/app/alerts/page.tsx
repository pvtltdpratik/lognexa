"use client"

import { BellOffIcon, CheckCheckIcon, EyeIcon, RotateCcwIcon, SearchIcon } from "lucide-react"
import { useSearchParams } from "next/navigation"
import * as React from "react"

import { AlertActionDialog } from "@/components/alert-action-dialog"
import { useAuth } from "@/components/auth"
import { OsBadge } from "@/components/endpoint-badges"
import { PageIntro } from "@/components/app-shell"
import { Pager } from "@/components/pager"
import { AlertStatusBadge, SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, SignInRequired, TableSkeleton } from "@/components/states"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatDateTime, formatShort, humanize } from "@/lib/format"
import { severityValues } from "@/lib/schemas"
import type { Alert, AlertDetail, AlertStatus } from "@/lib/types"

type Tab = AlertStatus | "all"

function renderResolution(data: AlertDetail) {
  if (data.status === "resolved")
    return (
      <div className="border-l-2 border-success bg-muted/40 p-3 text-xs">
        <div className="font-semibold">Resolved by {data.resolved_by} · {data.resolved_at && formatDateTime(data.resolved_at)}</div>
        <p className="mt-1 text-muted-foreground">{data.resolution_note}</p>
      </div>
    )
  if (data.status === "acknowledged" && data.resolution_note)
    return <p className="border-l-2 border-severity-medium p-2 text-xs text-muted-foreground">{data.resolution_note}</p>
  return null
}

function AlertActions({ alert, onAction }: { alert: Alert; onAction: (a: Alert, t: AlertStatus) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {alert.status === "open" && (
        <Button size="xs" variant="outline" onClick={() => onAction(alert, "acknowledged")}>
          <EyeIcon data-icon="inline-start" /> Acknowledge
        </Button>
      )}
      {alert.status !== "resolved" && (
        <Button size="xs" onClick={() => onAction(alert, "resolved")}>
          <CheckCheckIcon data-icon="inline-start" /> Resolve
        </Button>
      )}
      {alert.status !== "open" && (
        <Button size="xs" variant="ghost" onClick={() => onAction(alert, "open")}>
          <RotateCcwIcon data-icon="inline-start" /> Reopen
        </Button>
      )}
    </div>
  )
}

function AlertSheet({ id, version, onClose, onAction }: { id: number | null; version: number; onClose: () => void; onAction: (a: Alert, t: AlertStatus) => void }) {
  const { data, error, loading, reload } = useApi(() => (id ? api.alert(id) : Promise.resolve(null)), [id, version])
  return (
    <Sheet open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="flex flex-wrap items-center gap-3">
            Alert #{id} {data && <SeverityBadge severity={data.severity} />} {data && <AlertStatusBadge status={data.status} />}
          </SheetTitle>
          <SheetDescription>{data?.title ?? "Loading alert…"}</SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1">
          {loading && !data ? (
            <div className="flex flex-col gap-3 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}</div>
          ) : error ? (
            <div className="p-4"><ErrorState error={error} onRetry={reload} /></div>
          ) : data ? (
            <div className="flex flex-col gap-5 p-4 text-sm">
              <>
                  <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2">
                    <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Host</dt><dd>{data.hostname} {data.os_type && <span className="text-muted-foreground">({data.os_type})</span>}</dd>
                    <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Account</dt><dd>{data.username}</dd>
                    <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Events</dt><dd>{data.event_count} correlated event(s)</dd>
                  </dl>
                  {renderResolution(data)}
                  <Separator />
                  <pre className="border-l-2 border-primary bg-accent/40 p-3 font-sans text-xs whitespace-pre-wrap text-muted-foreground">{data.description}</pre>
                  {data.endpoint_event?.triggered_rules?.length ? (
                    <ul className="flex flex-col divide-y border">
                      {data.endpoint_event.triggered_rules.map((r) => (
                        <li key={r.code} className="flex items-start justify-between gap-3 p-2.5">
                          <div><span className="font-medium"><span className="mr-2 font-mono text-xs text-primary">{r.code}</span>{r.name}</span><div className="text-xs text-muted-foreground">{r.reason}</div></div>
                          <span className="tabular shrink-0 font-mono text-xs">+{r.points}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {data.related_events && data.related_events.length > 1 && (
                    <section className="flex flex-col gap-2">
                      <h4 className="text-sm font-semibold">Correlated events</h4>
                      <ul className="flex flex-col divide-y text-xs">
                        {data.related_events.map((e) => (
                          <li key={e.id} className="flex items-center justify-between gap-2 py-1.5">
                            <span>{humanize(e.event_type)} <span className="font-mono text-muted-foreground">{e.process_name || e.file_path || e.dst_ip || ""}</span></span>
                            <span className="tabular shrink-0 font-mono text-muted-foreground">{formatShort(e.timestamp)}</span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
              </>
            </div>
          ) : null}
        </ScrollArea>
        {data && (
          <SheetFooter className="border-t">
            <AlertActions alert={data} onAction={onAction} />
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  )
}

function AlertsView() {
  const params = useSearchParams()
  const { signedIn, ready } = useAuth()
  const focus = Number(params.get("focus")) || null
  const [tab, setTab] = React.useState<Tab>(focus ? "all" : "open")
  const [severity, setSeverity] = React.useState("")
  const [searchInput, setSearchInput] = React.useState("")
  const [sort, setSort] = React.useState("risk_desc")
  const [page, setPage] = React.useState(1)
  const [openId, setOpenId] = React.useState<number | null>(focus)
  const [action, setAction] = React.useState<{ alert: Alert; target: AlertStatus } | null>(null)
  const [version, setVersion] = React.useState(0)
  const search = useDebounced(searchInput.trim(), 350)
  const searchError = searchInput.length > 100 ? "Search must be 100 characters or fewer" : null
  const { data, error, loading, reload } = useApi(
    () => signedIn
      ? api.alerts({
          page, page_size: 20, sort, severity, source: "endpoint",
          status: tab === "all" ? undefined : tab,
          search: searchError ? undefined : search || undefined,
        })
      : Promise.resolve(null),
    [signedIn, page, sort, severity, tab, search, searchError, version]
  )

  const reset = () => setPage(1)
  const intro = (
    <PageIntro
      title="Alerts"
      description="Correlated endpoint detections whose risk crossed the threshold. Triage them by acknowledging and resolving with a note."
    />
  )
  if (ready && !signedIn) {
    return (
      <>
        {intro}
        <SignInRequired feature="Alert triage" />
      </>
    )
  }
  return (
    <>
      {intro}
      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          <Tabs value={tab} onValueChange={(v) => { setTab(v as Tab); reset() }}>
            <TabsList>
              <TabsTrigger value="open">Open</TabsTrigger>
              <TabsTrigger value="acknowledged">Acknowledged</TabsTrigger>
              <TabsTrigger value="resolved">Resolved</TabsTrigger>
              <TabsTrigger value="all">All</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
            <Field className="sm:max-w-sm" data-invalid={!!searchError}>
              <FieldLabel htmlFor="alert-search" className="text-xs">Search</FieldLabel>
              <InputGroup>
                <InputGroupAddon><SearchIcon /></InputGroupAddon>
                <InputGroupInput id="alert-search" placeholder="Title, host, account or IP" value={searchInput}
                  aria-invalid={!!searchError} onChange={(e) => { setSearchInput(e.target.value); reset() }} />
              </InputGroup>
              <FieldError>{searchError}</FieldError>
            </Field>
            <Field className="min-w-36 sm:w-44">
              <FieldLabel htmlFor="alert-sev" className="text-xs">Severity</FieldLabel>
              <NativeSelect id="alert-sev" value={severity} onChange={(e) => { setSeverity(e.target.value); reset() }} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption>
                {severityValues.map((s) => <NativeSelectOption key={s} value={s}>{humanize(s)}</NativeSelectOption>)}
              </NativeSelect>
            </Field>
            <Field className="min-w-36 sm:w-44">
              <FieldLabel htmlFor="alert-sort" className="text-xs">Sort</FieldLabel>
              <NativeSelect id="alert-sort" value={sort} onChange={(e) => { setSort(e.target.value); reset() }} className="w-full">
                <NativeSelectOption value="risk_desc">Highest risk</NativeSelectOption>
                <NativeSelectOption value="newest">Newest event</NativeSelectOption>
                <NativeSelectOption value="oldest">Oldest event</NativeSelectOption>
              </NativeSelect>
            </Field>
          </div>
        </CardContent>
      </Card>

      {!!error && <ErrorState error={error} onRetry={reload} />}
      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          {loading && !data ? (
            <TableSkeleton rows={8} cols={5} />
          ) : data && data.total === 0 ? (
            <EmptyState icon={BellOffIcon} title={tab === "open" ? "No open alerts" : "No alerts here"}
              description={tab === "open" ? "Every alert has been triaged, or no detection has fired yet." : "Nothing matches the current filters."} />
          ) : data ? (
            <>
              <Table className={loading ? "opacity-60 transition-opacity" : ""}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Alert</TableHead>
                    <TableHead>Host</TableHead>
                    <TableHead className="hidden md:table-cell">Event time</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead className="hidden sm:table-cell">Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="max-w-80">
                        <button className="flex items-center gap-2 text-left font-medium hover:text-primary" onClick={() => setOpenId(a.id)}>
                          <span className="font-mono text-xs text-muted-foreground">#{a.id}</span>{a.title}
                          {a.event_count && a.event_count > 1 ? <Badge variant="outline" className="px-1 py-0 text-[0.6rem]">×{a.event_count}</Badge> : null}
                        </button>
                        <div className="truncate font-mono text-xs text-muted-foreground">{a.resource} · {a.ip_address ?? ""}</div>
                      </TableCell>
                      <TableCell>
                        <span className="flex items-center gap-1.5">{a.os_type && <OsBadge os={a.os_type as "windows" | "linux"} />}</span>
                        <div className="text-xs text-muted-foreground">{a.hostname}</div>
                      </TableCell>
                      <TableCell className="hidden font-mono text-xs md:table-cell">{formatShort(a.timestamp)}</TableCell>
                      <TableCell>
                        <span className="flex items-center gap-2">
                          <SeverityBadge severity={a.severity} />
                          <span className="tabular font-mono text-xs">{a.risk_score.toFixed(0)}</span>
                        </span>
                      </TableCell>
                      <TableCell className="hidden sm:table-cell"><AlertStatusBadge status={a.status} /></TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end">
                          <AlertActions alert={a} onAction={(alert, target) => setAction({ alert, target })} />
                        </div>
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

      <AlertSheet id={openId} version={version} onClose={() => setOpenId(null)} onAction={(alert, target) => setAction({ alert, target })} />
      <AlertActionDialog
        alert={action?.alert ?? null}
        target={action?.target ?? null}
        onClose={() => setAction(null)}
        onDone={() => { setAction(null); setVersion((v) => v + 1) }}
      />
    </>
  )
}

export default function AlertsPage() {
  return (
    <React.Suspense fallback={<TableSkeleton rows={8} cols={5} />}>
      <AlertsView />
    </React.Suspense>
  )
}
