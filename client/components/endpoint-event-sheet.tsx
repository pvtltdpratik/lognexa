"use client"

import { FileWarningIcon, GitBranchIcon } from "lucide-react"

import { OsBadge } from "@/components/endpoint-badges"
import { SeverityBadge } from "@/components/severity"
import { ErrorState } from "@/components/states"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatDateTime, formatShort, humanize } from "@/lib/format"
import type { EndpointEvent, EndpointEventDetail } from "@/lib/types"

function Row({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  if (children === null || children === undefined || children === "") return null
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">{label}</dt>
      <dd className={mono ? "min-w-0 font-mono text-xs break-all" : "min-w-0 break-words"}>{children}</dd>
    </div>
  )
}

function Timeline({ events, currentId }: { events: EndpointEvent[]; currentId: number }) {
  if (events.length === 0) return <p className="text-sm text-muted-foreground">No correlated events within ±15 minutes.</p>
  const all = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return (
    <ol className="flex flex-col gap-0 border-l-2 border-border pl-4">
      {all.map((e) => {
        const current = e.id === currentId
        return (
          <li key={e.id} className="relative py-2">
            <span className="absolute -left-[1.3rem] top-3 size-2 rounded-full" style={{ backgroundColor: current ? "var(--primary)" : "var(--muted-foreground)" }} />
            <div className="flex items-baseline justify-between gap-2">
              <span className={current ? "text-sm font-semibold" : "text-sm"}>{humanize(e.event_type)}</span>
              <span className="tabular shrink-0 font-mono text-[0.7rem] text-muted-foreground">{formatShort(e.timestamp)}</span>
            </div>
            <div className="truncate font-mono text-xs text-muted-foreground">
              {e.process_name || e.file_path || (e.dst_ip ? `${e.dst_ip}:${e.dst_port ?? ""}` : e.username || e.source)}
            </div>
            {e.severity && e.risk_score ? <SeverityBadge severity={e.severity} className="mt-1 px-0 py-0 bg-transparent!" /> : null}
          </li>
        )
      })}
    </ol>
  )
}

function Body({ ev }: { ev: EndpointEventDetail }) {
  const w = 0.6
  return (
    <div className="flex flex-col gap-5 p-4">
      <dl className="divide-y">
        <Row label="Time">{formatDateTime(ev.timestamp)}</Row>
        <Row label="Host">{ev.device.hostname}</Row>
        <Row label="Source">{ev.source} · {humanize(ev.category)}</Row>
        <Row label="User">{ev.username}</Row>
        <Row label="Process" mono>{ev.process_name}{ev.pid ? ` (pid ${ev.pid})` : ""}</Row>
        <Row label="Path" mono>{ev.process_path}</Row>
        <Row label="Command" mono>{ev.command_line}</Row>
        <Row label="Parent" mono>{ev.parent_process}{ev.parent_pid ? ` (pid ${ev.parent_pid})` : ""}</Row>
        <Row label="Source IP" mono>{ev.src_ip}</Row>
        <Row label="Destination" mono>{ev.dst_ip ? `${ev.dst_ip}${ev.dst_port ? `:${ev.dst_port}` : ""}` : null}</Row>
        <Row label="File" mono>{ev.file_path}</Row>
        <Row label="Message">{ev.message}</Row>
      </dl>

      {ev.redacted && (
        <p className="flex items-center gap-2 border border-dashed p-2 text-xs text-muted-foreground">
          <FileWarningIcon className="size-3.5 shrink-0" /> Sensitive values in this event were redacted before storage.
        </p>
      )}

      <Separator />

      {ev.risk_score !== null && ev.triggered_rules.length >= 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Risk {ev.risk_score?.toFixed(0)}</h4>
            {ev.severity && <SeverityBadge severity={ev.severity} />}
          </div>
          {ev.triggered_rules.length > 0 ? (
            <ul className="flex flex-col divide-y border">
              {ev.triggered_rules.map((r) => (
                <li key={r.code} className="flex items-start justify-between gap-3 p-2.5 text-sm">
                  <div>
                    <span className="font-medium"><span className="mr-2 font-mono text-xs text-primary">{r.code}</span>{r.name}</span>
                    <div className="text-xs text-muted-foreground">{r.reason}</div>
                  </div>
                  <span className="tabular shrink-0 font-mono text-xs">+{r.points}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No rule fired for this event.</p>
          )}
          {ev.explanation && (
            <p className="border-l-2 border-primary bg-accent/40 p-3 text-xs text-muted-foreground">
              {ev.ml_is_anomaly !== null && (
                <span className="mb-1 block font-mono">
                  risk = {w} × {ev.rule_score?.toFixed(0)} {ev.ml_score ? `+ ${(1 - w).toFixed(1)} × ${ev.ml_score.toFixed(0)}` : "(pure rules)"} = {ev.risk_score?.toFixed(0)}
                </span>
              )}
              {ev.explanation}
            </p>
          )}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h4 className="flex items-center gap-2 text-sm font-semibold"><GitBranchIcon className="size-4 text-primary" /> Investigation timeline</h4>
        <Timeline events={[ev, ...ev.related]} currentId={ev.id} />
      </section>
    </div>
  )
}

export function EndpointEventSheet({ eventId, onOpenChange }: { eventId: number | null; onOpenChange: (o: boolean) => void }) {
  const { data, error, loading, reload } = useApi(() => (eventId ? api.endpointEvent(eventId) : Promise.resolve(null)), [eventId])
  return (
    <Sheet open={eventId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="flex flex-wrap items-center gap-3">
            {data ? humanize(data.event_type) : `Event #${eventId}`}
            {data?.severity && <SeverityBadge severity={data.severity} />}
          </SheetTitle>
          <SheetDescription>{data ? <span className="flex items-center gap-2"><OsBadge os={data.os_type} /> · {data.device.hostname}</span> : "Loading event…"}</SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1">
          {loading && !data ? (
            <div className="flex flex-col gap-3 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}</div>
          ) : error ? (
            <div className="p-4"><ErrorState error={error} onRetry={reload} /></div>
          ) : data ? (
            <Body ev={data} />
          ) : null}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
