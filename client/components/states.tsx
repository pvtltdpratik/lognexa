import { DatabaseZapIcon, KeyRoundIcon, RefreshCwIcon, SearchXIcon, type LucideIcon } from "lucide-react"
import * as React from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiError, errorMessage } from "@/lib/api"

export function ErrorState({ error, onRetry, title = "Could not load data" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const offline = error instanceof ApiError && (error.code === "network_error" || error.code === "database_error")
  return (
    <Alert variant="destructive">
      <DatabaseZapIcon />
      <AlertTitle>{offline ? "Backend unavailable" : title}</AlertTitle>
      <AlertDescription>
        <p>{errorMessage(error)}</p>
        {onRetry && (
          <Button variant="outline" size="xs" className="mt-3" onClick={onRetry}>
            <RefreshCwIcon data-icon="inline-start" /> Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

export function EmptyState({
  title,
  description,
  icon: Icon = SearchXIcon,
  action,
}: {
  title: string
  description: string
  icon?: LucideIcon
  action?: React.ReactNode
}) {
  return (
    <Empty className="bg-grid border border-dashed py-12">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  )
}

export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-8 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SignInRequired({ feature }: { feature: string }) {
  return (
    <EmptyState
      icon={KeyRoundIcon}
      title="Sign in required"
      description={`${feature} is protected. Use "Sign in" in the top bar with an analyst or admin token to continue.`}
    />
  )
}
