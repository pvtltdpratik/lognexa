"use client"

import { ActivityIcon, AlertTriangleIcon, BellRingIcon, LaptopIcon, ShieldPlusIcon, WrenchIcon } from "lucide-react"
import Link from "next/link"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts"

import { PageIntro } from "@/components/app-shell"
import { useAuth } from "@/components/auth"
import { OsBadge } from "@/components/endpoint-badges"
import { SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, SignInRequired } from "@/components/states"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { SEVERITIES, formatHour, formatShort, humanize, nf, severityColor, severityLabel } from "@/lib/format"
import type { EndpointOverview } from "@/lib/types"

const hourlyConfig = {
  events: { label: "Events", color: "var(--chart-4)" },
  flagged: { label: "Flagged by a rule", color: "var(--chart-1)" },
} satisfies ChartConfig

const categoryConfig = { count: { label: "Events", color: "var(--chart-2)" } } satisfies ChartConfig

function Stat({ title, value, hint, icon: Icon, accent }: { title: string; value: string; hint: string; icon: typeof LaptopIcon; accent?: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription className="text-xs font-semibold tracking-widest uppercase">{title}</CardDescription>
        <CardAction>
          <Icon className="size-4" style={{ color: accent ?? "var(--muted-foreground)" }} />
        </CardAction>
        <CardTitle className="tabular font-heading text-3xl font-semibold">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

function TopAlerts() {
  const { data } = useApi(() => api.alerts({ source: "endpoint", status: "open", sort: "risk_desc", page_size: 5 }), [])
  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BellRingIcon className="size-4 text-primary" /> Highest-risk open alerts</CardTitle>
        <CardDescription>Correlated detections that still need triage.</CardDescription>
        <CardAction>
          <Link href="/alerts" className={buttonVariants({ variant: "outline", size: "xs" })}>All alerts</Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        {data && data.items.length === 0 ? (
          <EmptyState icon={BellRingIcon} title="No open alerts" description="Every endpoint alert has been triaged." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alert</TableHead>
                <TableHead className="hidden sm:table-cell">Host</TableHead>
                <TableHead className="hidden md:table-cell">Event time</TableHead>
                <TableHead className="text-right">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.items ?? []).map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="max-w-72">
                    <Link href={`/alerts?focus=${a.id}`} className="font-medium hover:text-primary">{a.title}</Link>
                    {a.event_count && a.event_count > 1 ? <span className="ml-2 font-mono text-xs text-muted-foreground">×{a.event_count}</span> : null}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <span className="flex items-center gap-1.5">{a.os_type && <OsBadge os={a.os_type as "windows" | "linux"} />}{a.hostname}</span>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">{formatShort(a.timestamp)}</TableCell>
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-2">
                      <SeverityBadge severity={a.severity} />
                      <span className="tabular font-mono text-xs">{a.risk_score.toFixed(0)}</span>
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function Dashboard({ data }: { data: EndpointOverview }) {
  const online = data.devices_by_connection.online ?? 0
  const flagged24h = data.hourly.reduce((n, h) => n + h.flagged, 0)
  const sevData = SEVERITIES.map((s) => ({ severity: severityLabel[s], key: s, count: data.severity_counts_24h[s] ?? 0 }))
  const catData = Object.entries(data.category_counts_24h)
    .map(([category, count]) => ({ category: humanize(category), count }))
    .sort((a, b) => b.count - a.count)

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat title="Endpoints online" value={`${online} / ${data.devices_total}`} icon={LaptopIcon} accent="var(--success)"
          hint={`${data.devices_by_os.windows ?? 0} Windows · ${data.devices_by_os.linux ?? 0} Linux`} />
        <Stat title="Events (24h)" value={nf.format(data.events_24h)} icon={ActivityIcon}
          hint={`${nf.format(data.events_total)} collected in total`} />
        <Stat title="Open alerts" value={nf.format(data.open_endpoint_alerts)} icon={AlertTriangleIcon} accent="var(--severity-critical)"
          hint={`${nf.format(flagged24h)} events flagged by a rule in 24h`} />
        <Stat title="Collector issues" value={nf.format(data.collector_issues.length)} icon={WrenchIcon}
          accent={data.collector_issues.length ? "var(--severity-medium)" : undefined}
          hint={data.collector_issues.length ? "Missing permissions or unsupported sources" : "All collectors healthy"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Telemetry over the last 24 hours</CardTitle>
            <CardDescription>Events received per hour, and how many a detection rule flagged.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={hourlyConfig} className="aspect-auto h-64 w-full">
              <AreaChart data={data.hourly} margin={{ left: 0, right: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={false} tickFormatter={formatHour} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} width={40} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => formatHour(String(v))} />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Area dataKey="events" type="monotone" fill="var(--color-events)" fillOpacity={0.18} stroke="var(--color-events)" strokeWidth={2} />
                <Area dataKey="flagged" type="monotone" fill="var(--color-flagged)" fillOpacity={0.35} stroke="var(--color-flagged)" strokeWidth={2} />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Severity (24h)</CardTitle>
            <CardDescription>Scored events by severity band.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={{ count: { label: "Events" } }} className="aspect-auto h-48 w-full">
              <BarChart data={sevData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="severity" tickLine={false} axisLine={false} width={64} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" radius={0}>
                  {sevData.map((d) => <Cell key={d.key} fill={severityColor[d.key]} />)}
                </Bar>
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <TopAlerts />

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Event categories (24h)</CardTitle>
              <CardDescription>What the agents are collecting.</CardDescription>
            </CardHeader>
            <CardContent>
              {catData.length === 0 ? (
                <p className="text-sm text-muted-foreground">No events in the last 24 hours.</p>
              ) : (
                <ChartContainer config={categoryConfig} className="aspect-auto h-48 w-full">
                  <BarChart data={catData} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="category" tickLine={false} axisLine={false} width={96} tick={{ fontSize: 11 }} />
                    <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
                    <Bar dataKey="count" fill="var(--color-count)" />
                  </BarChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>

          {data.collector_issues.length > 0 && (
            <Card size="sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><WrenchIcon className="size-4 text-severity-medium" /> Collector issues</CardTitle>
                <CardDescription>Reported by agents in their latest heartbeat.</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col divide-y text-xs">
                  {data.collector_issues.map((i) => (
                    <li key={`${i.device_id}-${i.collector}`} className="flex flex-col gap-0.5 py-1.5">
                      <span><span className="font-medium">{i.hostname}</span> · <span className="font-mono">{i.collector}</span> · {humanize(i.status)}</span>
                      {i.detail && <span className="text-muted-foreground">{i.detail}</span>}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}

export default function OverviewPage() {
  const { signedIn, ready } = useAuth()
  const { data, error, loading, reload } = useApi(() => (signedIn ? api.endpointOverview() : Promise.resolve(null)), [signedIn])
  const intro = (
    <PageIntro title="Security overview" description="Live security telemetry from your enrolled Windows and Linux endpoints." />
  )

  if (ready && !signedIn) {
    return (
      <>
        {intro}
        <SignInRequired feature="The security overview" />
      </>
    )
  }
  return (
    <>
      {intro}
      {!!error && <ErrorState error={error} onRetry={reload} />}
      {(loading || !ready) && !data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className={i < 4 ? "h-32" : "h-64 sm:col-span-2"} />)}
        </div>
      )}
      {data && data.devices_total === 0 && (
        <EmptyState
          icon={ShieldPlusIcon}
          title="No endpoints enrolled yet"
          description="Create an enrolment token and install the agent on a Windows or Linux machine to start collecting telemetry."
          action={<Link href="/enrollment" className={buttonVariants({ size: "sm" })}>Enrol an endpoint</Link>}
        />
      )}
      {data && data.devices_total > 0 && <Dashboard data={data} />}
    </>
  )
}
