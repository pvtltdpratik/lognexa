"use client"

import { FlaskConicalIcon } from "lucide-react"
import Link from "next/link"

import { RiskExplanation } from "@/components/risk-explanation"
import { AlertStatusBadge, SeverityBadge } from "@/components/severity"
import { ErrorState } from "@/components/states"
import { buttonVariants } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatDateTime, humanize } from "@/lib/format"
import type { AccessLogDetail } from "@/lib/types"

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function Body({ log }: { log: AccessLogDetail }) {
  return (
    <div className="flex flex-col gap-6 p-4">
      <dl className="divide-y">
        <Row label="Timestamp"><span className="font-mono text-xs">{formatDateTime(log.timestamp)}</span></Row>
        <Row label="User">
          {log.user.full_name} <span className="text-muted-foreground">({log.username})</span>
          <div className="text-xs text-muted-foreground">{log.user.department} · {humanize(log.user.role)} · {log.user.shift} shift</div>
        </Row>
        <Row label="Action">{humanize(log.action)} · <span className="capitalize">{log.status}</span></Row>
        <Row label="Resource">
          <span className="font-mono text-xs">{log.resource}</span>{" "}
          <span className="text-xs text-muted-foreground">({log.resource_sensitivity})</span>
        </Row>
        <Row label="Source"><span className="font-mono text-xs">{log.ip_address}</span> · {log.city}, {log.country}</Row>
        <Row label="Device">{log.device}</Row>
        {log.alert && (
          <Row label="Alert">
            <span className="flex flex-wrap items-center gap-2">
              <AlertStatusBadge status={log.alert.status} />
              <Link href={`/alerts?focus=${log.alert.id}`} className={buttonVariants({ variant: "link", size: "xs" })}>
                Open alert #{log.alert.id}
              </Link>
            </span>
          </Row>
        )}
      </dl>
      <Separator />
      {log.risk ? (
        <RiskExplanation risk={log.risk} />
      ) : (
        <p className="text-sm text-muted-foreground">This event has not been analysed yet. Run an analysis from the Analysis page.</p>
      )}
      {log.injected_anomaly && (
        <p className="flex items-start gap-2 border border-dashed p-3 text-xs text-muted-foreground">
          <FlaskConicalIcon className="mt-0.5 size-3.5 shrink-0" />
          Ground truth (synthetic generator): this event was injected as a “{humanize(log.injected_anomaly)}” anomaly.
          The label is used only for evaluation, never as a detection input.
        </p>
      )}
    </div>
  )
}

export function LogDetailSheet({ logId, onOpenChange }: { logId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data, error, loading, reload } = useApi(
    () => (logId ? api.log(logId) : Promise.resolve(null)),
    [logId]
  )
  return (
    <Sheet open={logId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center gap-3">
            Event #{logId}
            {data?.severity && <SeverityBadge severity={data.severity} />}
          </SheetTitle>
          <SheetDescription>Full event context and the explanation of its risk score.</SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1">
          {loading && !data ? (
            <div className="flex flex-col gap-3 p-4">
              {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}
            </div>
          ) : error ? (
            <div className="p-4"><ErrorState error={error} onRetry={reload} /></div>
          ) : data ? (
            <Body log={data} />
          ) : null}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
