"use client"

import { KeyRoundIcon, RotateCwIcon, ShieldOffIcon } from "lucide-react"
import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { useAuth } from "@/components/auth"
import { CollectorStatusBadge, ConnectionBadge, OsBadge } from "@/components/endpoint-badges"
import { ErrorState } from "@/components/states"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "@/components/ui/toast"
import { useApi } from "@/hooks/use-api"
import { api, errorMessage } from "@/lib/api"
import { formatDateTime, formatShort, humanize } from "@/lib/format"

const bufferConfig = { buffer_pending: { label: "Buffered events", color: "var(--chart-1)" } } satisfies ChartConfig

export function DeviceDetailSheet({ deviceId, onOpenChange, onChanged }: { deviceId: number | null; onOpenChange: (o: boolean) => void; onChanged: () => void }) {
  const { role } = useAuth()
  const [version, setVersion] = React.useState(0)
  const { data, error, loading, reload } = useApi(() => (deviceId ? api.device(deviceId) : Promise.resolve(null)), [deviceId, version])
  const [confirmRevoke, setConfirmRevoke] = React.useState(false)
  const [reason, setReason] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  async function rotate() {
    if (!deviceId) return
    setBusy(true)
    try {
      await api.rotateDevice(deviceId)
      toast.add({ title: "Rotation requested", description: "The agent will rotate its credential on its next heartbeat.", type: "success" })
      setVersion((v) => v + 1)
      onChanged()
    } catch (e) {
      toast.add({ title: "Rotation failed", description: errorMessage(e), type: "error" })
    } finally {
      setBusy(false)
    }
  }

  async function revoke() {
    if (!deviceId) return
    setBusy(true)
    try {
      await api.revokeDevice(deviceId, reason)
      toast.add({ title: "Device revoked", type: "success" })
      setConfirmRevoke(false)
      setReason("")
      setVersion((v) => v + 1)
      onChanged()
    } catch (e) {
      toast.add({ title: "Revoke failed", description: errorMessage(e), type: "error" })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet open={deviceId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="flex flex-wrap items-center gap-3">
            {data?.hostname ?? `Device #${deviceId}`}
            {data && <ConnectionBadge connection={data.connection} />}
          </SheetTitle>
          <SheetDescription>{data ? <OsBadge os={data.os_type} /> : "Loading device…"}</SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1">
          {loading && !data ? (
            <div className="flex flex-col gap-3 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}</div>
          ) : error ? (
            <div className="p-4"><ErrorState error={error} onRetry={reload} /></div>
          ) : data ? (
            <div className="flex flex-col gap-5 p-4">
              <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">OS version</dt><dd>{data.os_version}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Agent</dt><dd className="font-mono text-xs">v{data.agent_version}{data.is_privileged ? " · privileged" : ""}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">IP address</dt><dd className="font-mono text-xs">{data.ip_address ?? "—"}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Device UID</dt><dd className="font-mono text-[0.7rem] break-all">{data.device_uid}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Enrolled</dt><dd>{formatDateTime(data.enrolled_at)}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Last seen</dt><dd>{data.last_seen_at ? formatDateTime(data.last_seen_at) : "never"}</dd>
                <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Events (24h)</dt><dd className="tabular font-mono">{data.events_24h} · {data.open_alerts} open alert(s)</dd>
                {data.status === "revoked" && (
                  <>
                    <dt className="text-xs font-semibold tracking-wider text-destructive uppercase">Revoked</dt>
                    <dd className="text-destructive">{data.revoked_reason} ({data.revoked_at && formatShort(data.revoked_at)})</dd>
                  </>
                )}
              </dl>

              <section className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">Collector health</h4>
                <Table>
                  <TableHeader>
                    <TableRow><TableHead>Collector</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Events</TableHead></TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.collectors.length === 0 ? (
                      <TableRow><TableCell colSpan={3} className="text-xs text-muted-foreground">No heartbeat received yet.</TableCell></TableRow>
                    ) : data.collectors.map((c) => (
                      <TableRow key={c.name}>
                        <TableCell className="font-mono text-xs">{c.name}{c.detail && <div className="text-[0.7rem] text-muted-foreground">{c.detail}</div>}</TableCell>
                        <TableCell><CollectorStatusBadge status={c.status} /></TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">{c.events_collected}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>

              {data.heartbeats.length > 1 && (
                <section className="flex flex-col gap-2">
                  <h4 className="text-sm font-semibold">Buffer depth (recent heartbeats)</h4>
                  <ChartContainer config={bufferConfig} className="aspect-auto h-32 w-full">
                    <AreaChart data={data.heartbeats} margin={{ left: 0, right: 8 }}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="received_at" tickLine={false} axisLine={false} tickFormatter={(v) => formatShort(String(v))} minTickGap={40} />
                      <YAxis tickLine={false} axisLine={false} width={28} />
                      <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => formatDateTime(String(v))} />} />
                      <Area dataKey="buffer_pending" type="monotone" stroke="var(--color-buffer_pending)" fill="var(--color-buffer_pending)" fillOpacity={0.2} />
                    </AreaChart>
                  </ChartContainer>
                </section>
              )}

              {Object.keys(data.category_counts).length > 0 && (
                <section className="flex flex-col gap-2">
                  <h4 className="text-sm font-semibold">Events by category (all time)</h4>
                  <ul className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                    {Object.entries(data.category_counts).map(([cat, n]) => (
                      <li key={cat} className="flex items-center justify-between border px-2 py-1.5">
                        <span className="capitalize">{humanize(cat)}</span>
                        <span className="tabular font-mono">{n}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          ) : null}
        </ScrollArea>
        {data && role === "admin" && data.status === "active" && (
          <SheetFooter className="flex-row border-t">
            <Button variant="outline" size="sm" onClick={rotate} disabled={busy || data.rotation_requested}>
              <RotateCwIcon data-icon="inline-start" /> {data.rotation_requested ? "Rotation pending" : "Rotate credential"}
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setConfirmRevoke(true)} disabled={busy}>
              <ShieldOffIcon data-icon="inline-start" /> Revoke
            </Button>
          </SheetFooter>
        )}
        {data && role !== "admin" && (
          <SheetFooter className="border-t text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><KeyRoundIcon className="size-3" /> Credential actions require the admin role.</span>
          </SheetFooter>
        )}
      </SheetContent>

      <AlertDialog open={confirmRevoke} onOpenChange={(o) => !o && !busy && setConfirmRevoke(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke {data?.hostname}?</AlertDialogTitle>
            <AlertDialogDescription>
              The device credential stops working immediately. The agent must be re-enrolled with a new token to report again.
              Collected telemetry is kept.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Field>
            <FieldLabel htmlFor="revoke-reason">Reason</FieldLabel>
            <Input id="revoke-reason" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. decommissioned / suspected compromise" />
          </Field>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={revoke} disabled={busy || reason.trim().length < 3}>Revoke device</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sheet>
  )
}
