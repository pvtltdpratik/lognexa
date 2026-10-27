"use client"

import {
  ActivityIcon,
  BellRingIcon,
  BrainCircuitIcon,
  GaugeIcon,
  LayoutDashboardIcon,
  ScrollTextIcon,
} from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import * as React from "react"

import { Wordmark } from "@/components/brand/logo"
import { ThemeToggle } from "@/components/theme-provider"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboardIcon },
  { href: "/logs", label: "Access logs", icon: ScrollTextIcon },
  { href: "/alerts", label: "Alerts", icon: BellRingIcon },
  { href: "/risk", label: "Risk scores", icon: GaugeIcon },
  { href: "/analysis", label: "Analysis & data", icon: BrainCircuitIcon },
]

function HealthIndicator() {
  const { data, error, loading } = useApi(() => api.health(), [])
  const ok = data?.database === "ok"
  const label = loading ? "Checking API…" : error ? "API offline" : ok ? `API online · ${data?.database_backend}` : "Database error"
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
            <span
              className={cn("size-2 rounded-full", loading ? "animate-pulse bg-muted-foreground" : ok ? "bg-success" : "bg-destructive")}
            />
            <span className="hidden sm:inline">{label}</span>
          </span>
        }
      />
      <TooltipContent>
        {data?.counts ? `${data.counts.logs} logs · ${data.counts.alerts} alerts · v${data.version}` : label}
      </TooltipContent>
    </Tooltip>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const current = NAV.find((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader className="h-16 justify-center border-b border-sidebar-border px-3">
          <Link href="/" className="overflow-hidden" aria-label="Lognexa home">
            <Wordmark />
          </Link>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Monitoring</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={item === current}
                      tooltip={item.label}
                      render={<Link href={item.href} />}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="border-t border-sidebar-border p-3 text-[0.65rem] leading-relaxed text-muted-foreground group-data-[collapsible=icon]:hidden">
          <span className="flex items-center gap-1.5 font-semibold tracking-widest uppercase">
            <ActivityIcon className="size-3 text-primary" /> Prototype
          </span>
          Student project · 100% synthetic data. Not production security software.
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur md:px-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-base font-semibold tracking-tight">{current?.label ?? "Lognexa"}</h1>
          <div className="ml-auto flex items-center gap-3">
            <HealthIndicator />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex flex-1 flex-col gap-6 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export function PageIntro({ title, description, actions }: { title: string; description: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}
