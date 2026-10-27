"use client"

import { AlertTriangleIcon, LaptopIcon, MonitorIcon, WifiIcon } from "lucide-react"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { useAuth } from "@/components/auth"
import { DeviceDetailSheet } from "@/components/device-detail-sheet"
import { CollectorStatusBadge, ConnectionBadge, OsBadge } from "@/components/endpoint-badges"
import { EmptyState, ErrorState, SignInRequired, TableSkeleton } from "@/components/states"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatRelative } from "@/lib/format"
import { SearchIcon } from "lucide-react"

function Stat({ title, value, hint, icon: Icon }: { title: string; value: string; hint: string; icon: typeof LaptopIcon }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription className="text-xs font-semibold tracking-widest uppercase">{title}</CardDescription>
        <CardTitle className="tabular font-heading text-3xl font-semibold">{value}</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="size-4" /> {hint}
      </CardContent>
    </Card>
  )
}

export default function EndpointsPage() {
  const { signedIn, ready } = useAuth()
  const [os, setOs] = React.useState("")
  const [connection, setConnection] = React.useState("")
  const [searchInput, setSearchInput] = React.useState("")
  const [selected, setSelected] = React.useState<number | null>(null)
  const [version, setVersion] = React.useState(0)
  const search = useDebounced(searchInput.trim(), 300)

  const overview = useApi(() => (signedIn ? api.endpointOverview() : Promise.resolve(null)), [signedIn, version])
  const devices = useApi(
    () => (signedIn ? api.devices({ os_type: os, connection, search: search || undefined }) : Promise.resolve(null)),
    [signedIn, os, connection, search, version]
  )

  if (ready && !signedIn) {
    return (
      <>
        <PageIntro title="Endpoints" description="Inventory and health of enrolled Windows and Linux agents." />
        <SignInRequired feature="The endpoint inventory" />
      </>
    )
  }

  const ov = overview.data
  return (
    <>
      <PageIntro title="Endpoints" description="Inventory and health of enrolled Windows and Linux agents." />

      {ov && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat title="Enrolled devices" value={String(ov.devices_total)} icon={LaptopIcon}
            hint={`${ov.devices_by_os.windows ?? 0} Windows · ${ov.devices_by_os.linux ?? 0} Linux`} />
          <Stat title="Online" value={String(ov.devices_by_connection.online ?? 0)} icon={WifiIcon}
            hint={`${ov.devices_by_connection.stale ?? 0} stale · ${ov.devices_by_connection.offline ?? 0} offline`} />
          <Stat title="Events (24h)" value={ov.events_24h.toLocaleString()} icon={MonitorIcon}
            hint={`${ov.events_total.toLocaleString()} total collected`} />
          <Stat title="Open endpoint alerts" value={String(ov.open_endpoint_alerts)} icon={AlertTriangleIcon}
            hint={`${ov.collector_issues.length} collector issue(s)`} />
        </div>
      )}

      {ov && ov.collector_issues.length > 0 && (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-sm">Collector issues</CardTitle>
            <CardDescription>Collectors reporting a problem — usually missing privilege or an absent log source.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y text-sm">
              {ov.collector_issues.slice(0, 8).map((i, idx) => (
                <li key={idx} className="flex items-center justify-between gap-3 py-2">
                  <span><span className="font-medium">{i.hostname}</span> <span className="font-mono text-xs text-muted-foreground">{i.collector}</span></span>
                  <span className="flex items-center gap-2"><span className="hidden text-xs text-muted-foreground sm:inline">{i.detail}</span><CollectorStatusBadge status={i.status} /></span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card size="sm">
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <Field className="sm:max-w-sm">
              <FieldLabel htmlFor="ep-search" className="text-xs">Search</FieldLabel>
              <InputGroup>
                <InputGroupAddon><SearchIcon /></InputGroupAddon>
                <InputGroupInput id="ep-search" placeholder="Hostname, IP or OS" value={searchInput} maxLength={100} onChange={(e) => setSearchInput(e.target.value)} />
              </InputGroup>
            </Field>
            <Field className="sm:w-40">
              <FieldLabel htmlFor="ep-os" className="text-xs">OS</FieldLabel>
              <NativeSelect id="ep-os" value={os} onChange={(e) => setOs(e.target.value)} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption>
                <NativeSelectOption value="windows">Windows</NativeSelectOption>
                <NativeSelectOption value="linux">Linux</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Field className="sm:w-40">
              <FieldLabel htmlFor="ep-conn" className="text-xs">Connection</FieldLabel>
              <NativeSelect id="ep-conn" value={connection} onChange={(e) => setConnection(e.target.value)} className="w-full">
                <NativeSelectOption value="">All</NativeSelectOption>
                <NativeSelectOption value="online">Online</NativeSelectOption>
                <NativeSelectOption value="stale">Stale</NativeSelectOption>
                <NativeSelectOption value="offline">Offline</NativeSelectOption>
                <NativeSelectOption value="revoked">Revoked</NativeSelectOption>
              </NativeSelect>
            </Field>
          </div>

          {devices.error ? <ErrorState error={devices.error} onRetry={devices.reload} /> : devices.loading && !devices.data ? (
            <TableSkeleton rows={6} cols={6} />
          ) : devices.data && devices.data.length === 0 ? (
            <EmptyState icon={LaptopIcon} title="No endpoints" description="Enrol a device from the Enrolment page, or adjust the filters." />
          ) : devices.data ? (
            <Table className={devices.loading ? "opacity-60" : ""}>
              <TableHeader>
                <TableRow>
                  <TableHead>Host</TableHead>
                  <TableHead>OS</TableHead>
                  <TableHead>Connection</TableHead>
                  <TableHead className="hidden md:table-cell">Last seen</TableHead>
                  <TableHead className="text-right">Events 24h</TableHead>
                  <TableHead className="text-right">Open alerts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {devices.data.map((d) => (
                  <TableRow key={d.id} className="cursor-pointer" tabIndex={0} onClick={() => setSelected(d.id)}
                    onKeyDown={(e) => e.key === "Enter" && setSelected(d.id)}>
                    <TableCell>
                      <div className="font-medium">{d.hostname}</div>
                      <div className="font-mono text-xs text-muted-foreground">{d.ip_address ?? d.device_uid.slice(0, 8)}</div>
                    </TableCell>
                    <TableCell><OsBadge os={d.os_type} /></TableCell>
                    <TableCell><ConnectionBadge connection={d.connection} /></TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground md:table-cell">{d.last_seen_at ? formatRelative(d.last_seen_at) : "never"}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{d.events_24h}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{d.open_alerts}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>

      <DeviceDetailSheet deviceId={selected} onOpenChange={(o) => !o && setSelected(null)} onChanged={() => setVersion((v) => v + 1)} />
    </>
  )
}
