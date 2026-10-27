import { z } from "zod"

// Client-side validation mirrors the server rules in server/app/schemas.py.
// The server re-validates everything; these exist for fast inline feedback.

export const severityValues = ["low", "medium", "high", "critical"] as const
export const alertStatusValues = ["open", "acknowledged", "resolved"] as const

export const alertUpdateSchema = z
  .object({
    status: z.enum(alertStatusValues),
    resolved_by: z.string().trim().max(80, "Name must be 80 characters or fewer").optional(),
    resolution_note: z.string().trim().max(500, "Note must be 500 characters or fewer").optional(),
  })
  .superRefine((v, ctx) => {
    if (v.status !== "resolved") return
    if (!v.resolved_by || v.resolved_by.length < 2)
      ctx.addIssue({ code: "custom", path: ["resolved_by"], message: "Enter the analyst name (at least 2 characters)" })
    if (!v.resolution_note || v.resolution_note.length < 10)
      ctx.addIssue({ code: "custom", path: ["resolution_note"], message: "Describe the resolution (at least 10 characters)" })
  })
export type AlertUpdateInput = z.infer<typeof alertUpdateSchema>
