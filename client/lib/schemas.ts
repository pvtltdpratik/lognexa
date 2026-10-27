import { z } from "zod"

// Client-side validation mirrors the server rules in server/app/schemas.py.
// The server re-validates everything; these exist for fast inline feedback.

export const severityValues = ["low", "medium", "high", "critical"] as const
export const alertStatusValues = ["open", "acknowledged", "resolved"] as const
export const actionValues = ["login", "logout", "file_read", "file_write", "download", "admin_action"] as const
export const logStatusValues = ["success", "failure", "denied"] as const
export const sensitivityValues = ["public", "internal", "confidential", "restricted"] as const

const optionalEnum = <T extends readonly [string, ...string[]]>(values: T) =>
  z.union([z.enum(values), z.literal("")]).optional()

export const logFiltersSchema = z
  .object({
    search: z.string().trim().max(100, "Search must be 100 characters or fewer").optional(),
    action: optionalEnum(actionValues),
    status: optionalEnum(logStatusValues),
    sensitivity: optionalEnum(sensitivityValues),
    severity: optionalEnum(severityValues),
    start: z.string().optional(),
    end: z.string().optional(),
  })
  .refine((v) => !v.start || !v.end || v.start <= v.end, {
    message: "End date must be on or after the start date",
    path: ["end"],
  })
export type LogFilters = z.infer<typeof logFiltersSchema>

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

export const analyzeSchema = z.object({
  contamination: z.number({ error: "Enter a number" }).min(0.01, "Minimum is 0.01").max(0.2, "Maximum is 0.2"),
  alert_threshold: z.number({ error: "Enter a number" }).min(1, "Minimum is 1").max(100, "Maximum is 100"),
  rule_weight: z.number({ error: "Enter a number" }).min(0, "Minimum is 0").max(1, "Maximum is 1"),
})
export type AnalyzeInput = z.infer<typeof analyzeSchema>

export const datasetSchema = z
  .object({
    seed: z.number({ error: "Enter a whole number" }).int("Must be a whole number").min(0).max(2147483647),
    n_users: z.number({ error: "Enter a whole number" }).int("Must be a whole number").min(6, "At least 6 users").max(500, "At most 500 users"),
    days: z.number({ error: "Enter a whole number" }).int("Must be a whole number").min(1, "At least 1 day").max(90, "At most 90 days"),
    n_records: z.number({ error: "Enter a whole number" }).int("Must be a whole number").min(200, "At least 200 records").max(50000, "At most 50,000 records"),
  })
  .refine((v) => v.n_records >= v.n_users * 5, {
    message: "Records must be at least 5 × users",
    path: ["n_records"],
  })
export type DatasetInput = z.infer<typeof datasetSchema>
