"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import * as React from "react"
import { Controller, useForm } from "react-hook-form"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { ApiError, api, errorMessage } from "@/lib/api"
import { alertUpdateSchema, type AlertUpdateInput } from "@/lib/schemas"
import type { Alert, AlertStatus } from "@/lib/types"

const COPY: Record<AlertStatus, { title: string; verb: string; description: string }> = {
  resolved: {
    title: "Resolve alert",
    verb: "Resolve",
    description: "Record who investigated the alert and what was found. Both fields are required.",
  },
  acknowledged: {
    title: "Acknowledge alert",
    verb: "Acknowledge",
    description: "Mark the alert as under investigation. A note is optional.",
  },
  open: {
    title: "Reopen alert",
    verb: "Reopen",
    description: "Move the alert back to the open queue. Any previous resolution is cleared.",
  },
}

export function AlertActionDialog({
  alert,
  target,
  onClose,
  onDone,
}: {
  alert: Alert | null
  target: AlertStatus | null
  onClose: () => void
  onDone: (updated: Alert) => void
}) {
  const open = alert !== null && target !== null
  const form = useForm<AlertUpdateInput>({
    resolver: zodResolver(alertUpdateSchema),
    defaultValues: { status: "resolved", resolved_by: "", resolution_note: "" },
    mode: "onTouched",
  })

  React.useEffect(() => {
    if (open) form.reset({ status: target, resolved_by: "", resolution_note: "" })
  }, [open, target, form])

  if (!target) return null
  const copy = COPY[target]
  const isResolve = target === "resolved"

  async function onSubmit(values: AlertUpdateInput) {
    if (!alert) return
    try {
      const payload: AlertUpdateInput = {
        status: values.status,
        resolution_note: values.resolution_note || undefined,
        resolved_by: isResolve ? values.resolved_by : undefined,
      }
      const updated = await api.updateAlert(alert.id, payload)
      toast.add({ title: `Alert #${alert.id} ${updated.status}`, type: "success" })
      onDone(updated)
    } catch (e) {
      // Map server-side field errors back onto the form when possible.
      if (e instanceof ApiError && e.code === "validation_error") {
        for (const d of e.details) {
          const field = (["resolution_note", "resolved_by"] as const).find((f) => d.field === f || d.message.startsWith(f))
          if (field) form.setError(field, { message: d.message })
        }
      }
      toast.add({ title: "Update failed", description: errorMessage(e), type: "error" })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-6">
          <DialogHeader>
            <DialogTitle>
              {copy.title} #{alert?.id}
            </DialogTitle>
            <DialogDescription>{copy.description}</DialogDescription>
          </DialogHeader>
          <FieldGroup>
            {isResolve && (
              <Controller
                control={form.control}
                name="resolved_by"
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="resolved_by">Analyst name</FieldLabel>
                    <Input id="resolved_by" {...field} value={field.value ?? ""} aria-invalid={fieldState.invalid} maxLength={80} autoComplete="name" />
                    <FieldError errors={[fieldState.error]} />
                  </Field>
                )}
              />
            )}
            <Controller
              control={form.control}
              name="resolution_note"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="resolution_note">{isResolve ? "Resolution note" : "Note (optional)"}</FieldLabel>
                  <Textarea
                    id="resolution_note"
                    rows={4}
                    {...field}
                    value={field.value ?? ""}
                    aria-invalid={fieldState.invalid}
                    maxLength={500}
                    placeholder={isResolve ? "e.g. Confirmed with the user – travelling, legitimate VPN login." : ""}
                  />
                  <FieldDescription>{(field.value ?? "").length}/500 characters</FieldDescription>
                  <FieldError errors={[fieldState.error]} />
                </Field>
              )}
            />
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={form.formState.isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting && <Spinner data-icon="inline-start" />}
              {copy.verb}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
