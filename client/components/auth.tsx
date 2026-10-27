"use client"

import { KeyRoundIcon, LogOutIcon, ShieldCheckIcon } from "lucide-react"
import * as React from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { ApiError, api, auth, errorMessage } from "@/lib/api"

interface AuthState {
  role: "analyst" | "admin" | null
  signedIn: boolean
  ready: boolean
  signOut: () => void
}

const AuthContext = React.createContext<AuthState>({ role: null, signedIn: false, ready: false, signOut: () => {} })

const noopSubscribe = () => () => {}

export function useAuth() {
  return React.useContext(AuthContext)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // The token lives outside React (localStorage); subscribe to it reactively.
  const token = React.useSyncExternalStore(auth.subscribe, auth.get, () => null)
  const [resolved, setResolved] = React.useState<{ token: string | null; role: "analyst" | "admin" | null }>({
    token: null,
    role: null,
  })

  React.useEffect(() => {
    let active = true
    // State is only updated inside the promise callback (never synchronously in
    // the effect body), so a token change doesn't trigger a cascading render.
    const lookup = token ? api.me().then((m) => m.role).catch(() => null) : Promise.resolve(null)
    lookup.then((role) => active && setResolved({ token, role }))
    return () => {
      active = false
    }
  }, [token])

  // The hydration render uses the server snapshot (no token), which would briefly
  // look like "signed out". Only report ready on the client, once the current
  // token has been resolved (verified or rejected).
  const hydrated = React.useSyncExternalStore(noopSubscribe, () => true, () => false)
  const ready = hydrated && resolved.token === token
  const role = ready ? resolved.role : null
  const value: AuthState = { role, signedIn: ready && role !== null, ready, signOut: () => auth.set(null) }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function SignInButton() {
  const { signedIn, role, signOut } = useAuth()
  const [open, setOpen] = React.useState(false)
  const [value, setValue] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    auth.set(value.trim())
    try {
      const m = await api.me()
      toast.add({ title: `Signed in as ${m.role}`, type: "success" })
      setOpen(false)
      setValue("")
    } catch (err) {
      auth.set(null)
      setError(err instanceof ApiError && err.status === 401 ? "That token is not valid." : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (signedIn) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="gap-1 border px-2 py-1" style={{ color: "var(--success)", borderColor: "color-mix(in oklch, var(--success) 40%, transparent)" }}>
          <ShieldCheckIcon className="size-3" /> {role}
        </Badge>
        <Button variant="ghost" size="icon-sm" aria-label="Sign out" onClick={signOut}>
          <LogOutIcon />
        </Button>
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm"><KeyRoundIcon data-icon="inline-start" /> Sign in</Button>} />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="flex flex-col gap-6">
          <DialogHeader>
            <DialogTitle>Sign in for endpoint monitoring</DialogTitle>
            <DialogDescription>
              Endpoint inventory, telemetry and endpoint alerts require an analyst or admin token
              (configured on the server as <code className="font-mono text-xs">LOGNEXA_ANALYST_TOKEN</code> /
              <code className="font-mono text-xs"> LOGNEXA_ADMIN_TOKEN</code>).
            </DialogDescription>
          </DialogHeader>
          <Field data-invalid={!!error}>
            <FieldLabel htmlFor="token">Access token</FieldLabel>
            <Input id="token" type="password" autoComplete="off" value={value} aria-invalid={!!error}
              onChange={(e) => setValue(e.target.value)} placeholder="paste your token" />
            <FieldDescription>Stored only in this browser; sent as a bearer token to the API.</FieldDescription>
            <FieldError>{error}</FieldError>
          </Field>
          <DialogFooter>
            <Button type="submit" disabled={busy || !value.trim()}>
              {busy && <Spinner data-icon="inline-start" />} Sign in
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
