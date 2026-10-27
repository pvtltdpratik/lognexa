"use client"

import { CheckIcon, CopyIcon, KeyRoundIcon, PlusIcon, TerminalIcon } from "lucide-react"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { useAuth } from "@/components/auth"
import { EmptyState, ErrorState, SignInRequired, TableSkeleton } from "@/components/states"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "@/components/ui/toast"
import { useApi } from "@/hooks/use-api"
import { api, errorMessage } from "@/lib/api"
import { formatShort } from "@/lib/format"
import type { EnrollmentTokenCreated } from "@/lib/types"

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false)
  return (
    <Button variant="outline" size="xs" onClick={() => {
      navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
    }}>
      {copied ? <CheckIcon data-icon="inline-start" /> : <CopyIcon data-icon="inline-start" />} {copied ? "Copied" : "Copy"}
    </Button>
  )
}

export default function EnrollmentPage() {
  const { signedIn, ready, role } = useAuth()
  const [label, setLabel] = React.useState("")
  const [maxUses, setMaxUses] = React.useState(1)
  const [hours, setHours] = React.useState(24)
  const [busy, setBusy] = React.useState(false)
  const [created, setCreated] = React.useState<EnrollmentTokenCreated | null>(null)
  const [version, setVersion] = React.useState(0)

  const isAdmin = role === "admin"
  const tokens = useApi(() => (isAdmin ? api.enrollmentTokens() : Promise.resolve(null)), [isAdmin, version])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const token = await api.createEnrollmentToken({ label: label.trim(), max_uses: maxUses, expires_in_hours: hours })
      setCreated(token)
      setLabel("")
      setVersion((v) => v + 1)
      toast.add({ title: "Enrolment token created", type: "success" })
    } catch (err) {
      toast.add({ title: "Could not create token", description: errorMessage(err), type: "error" })
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id: number) {
    try {
      await api.revokeEnrollmentToken(id)
      setVersion((v) => v + 1)
    } catch (err) {
      toast.add({ title: "Revoke failed", description: errorMessage(err), type: "error" })
    }
  }

  if (ready && !signedIn) {
    return (
      <>
        <PageIntro title="Enrolment" description="Issue enrolment tokens for new endpoint agents." />
        <SignInRequired feature="Agent enrolment" />
      </>
    )
  }
  if (ready && !isAdmin) {
    return (
      <>
        <PageIntro title="Enrolment" description="Issue enrolment tokens for new endpoint agents." />
        <EmptyState icon={KeyRoundIcon} title="Admin role required" description="Enrolment-token management is restricted to the admin role." />
      </>
    )
  }

  const apiBase = typeof window !== "undefined" ? (process.env.NEXT_PUBLIC_API_URL ?? "https://your-server:8000") : "https://your-server:8000"

  return (
    <>
      <PageIntro title="Enrolment" description="Create one-time tokens that let a new agent enrol and receive its own per-device credential." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <form onSubmit={create} className="contents">
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><PlusIcon className="size-4 text-primary" /> New enrolment token</CardTitle>
              <CardDescription>The plaintext token is shown once. Only its hash is stored on the server.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Field>
                <FieldLabel htmlFor="label">Label</FieldLabel>
                <Input id="label" value={label} maxLength={80} required placeholder="e.g. Finance laptops" onChange={(e) => setLabel(e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="uses">Max uses</FieldLabel>
                  <Input id="uses" type="number" min={1} max={100} value={maxUses} onChange={(e) => setMaxUses(Math.max(1, Number(e.target.value) || 1))} />
                  <FieldDescription>1–100 devices</FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="hours">Expires in (hours)</FieldLabel>
                  <Input id="hours" type="number" min={1} max={720} value={hours} onChange={(e) => setHours(Math.max(1, Number(e.target.value) || 1))} />
                </Field>
              </div>
              <Button type="submit" disabled={busy || label.trim().length < 2} className="self-start">
                {busy ? <Spinner data-icon="inline-start" /> : <KeyRoundIcon data-icon="inline-start" />} Create token
              </Button>
            </CardContent>
          </form>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><TerminalIcon className="size-4 text-primary" /> Enrol an agent</CardTitle>
            <CardDescription>Install the agent, then run the command below with a token from the left.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {created ? (
              <div className="flex flex-col gap-2 border border-primary bg-accent/40 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-widest uppercase">Token (shown once)</span>
                  <CopyButton text={created.token} />
                </div>
                <code className="font-mono text-xs break-all">{created.token}</code>
              </div>
            ) : (
              <p className="text-muted-foreground">Create a token to see it here. It cannot be retrieved later.</p>
            )}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Linux</span>
              <code className="block overflow-x-auto bg-muted p-2 font-mono text-xs">
                sudo LOGNEXA_SERVER_URL={apiBase} LOGNEXA_ENROLL_TOKEN=&lt;token&gt; lognexa-agent run
              </code>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Windows (PowerShell, admin)</span>
              <code className="block overflow-x-auto bg-muted p-2 font-mono text-xs">
                .\install-windows.ps1 -ServerUrl &quot;{apiBase}&quot; -EnrollToken &quot;&lt;token&gt;&quot;
              </code>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Issued tokens</CardTitle>
          <CardDescription>Unused, non-expired tokens can still enrol devices. Revoke any that leak.</CardDescription>
        </CardHeader>
        <CardContent>
          {tokens.error ? <ErrorState error={tokens.error} onRetry={tokens.reload} /> : !tokens.data ? <TableSkeleton rows={4} cols={5} /> : tokens.data.length === 0 ? (
            <EmptyState title="No tokens yet" description="Create your first enrolment token above." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow><TableHead>Label</TableHead><TableHead>Prefix</TableHead><TableHead>Uses</TableHead><TableHead>Expires</TableHead><TableHead>Status</TableHead><TableHead /></TableRow>
              </TableHeader>
              <TableBody>
                {tokens.data.map((t) => {
                  const expired = new Date(t.expires_at) < new Date()
                  const exhausted = t.uses >= t.max_uses
                  const active = !t.revoked && !expired && !exhausted
                  return (
                    <TableRow key={t.id}>
                      <TableCell className="font-medium">{t.label}</TableCell>
                      <TableCell className="font-mono text-xs">{t.token_prefix}…</TableCell>
                      <TableCell className="tabular font-mono text-xs">{t.uses}/{t.max_uses}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatShort(t.expires_at)}</TableCell>
                      <TableCell>
                        <Badge variant={active ? "secondary" : "outline"} className={active ? "" : "text-muted-foreground"}>
                          {t.revoked ? "revoked" : expired ? "expired" : exhausted ? "used up" : "active"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {active && <Button variant="ghost" size="xs" onClick={() => revoke(t.id)}>Revoke</Button>}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
