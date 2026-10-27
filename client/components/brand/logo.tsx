import { cn } from "@/lib/utils"

/**
 * Lognexa mark: a log "card" with a watching eye wired into circuit traces,
 * redrawn as a crisp SVG from the original raster logo (public/logo.jpg).
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" className={cn("size-8", className)}>
      <g stroke="var(--primary)" strokeLinecap="round">
        <path d="M2 12h7M4 17h5M1 22h8M3 27h6M2 32h7M5 37h4" strokeWidth="1.4" opacity="0.7" />
        <rect x="11" y="5" width="32" height="38" rx="4" strokeWidth="2.2" />
        <path d="M15 24c3.2-5 7-7.5 12-7.5s8.8 2.5 12 7.5c-3.2 5-7 7.5-12 7.5S18.2 29 15 24Z" strokeWidth="2" />
        <path d="M22 17v-3.5M27 16.5v-4M32 17v-3.5M22 31v3.5M27 31.5v4M32 31v3.5" strokeWidth="1.4" />
      </g>
      <g fill="var(--primary)">
        <circle cx="27" cy="24" r="4.2" />
        <circle cx="22" cy="12.5" r="1.3" />
        <circle cx="32" cy="12.5" r="1.3" />
        <circle cx="22" cy="35.5" r="1.3" />
        <circle cx="32" cy="35.5" r="1.3" />
      </g>
      <circle cx="27" cy="24" r="1.7" fill="var(--background)" />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="flex flex-col leading-none">
        <span className="font-heading text-lg font-semibold tracking-tight">
          Log<span className="text-primary">nexa</span>
        </span>
        <span className="text-[0.6rem] font-medium tracking-[0.2em] text-muted-foreground uppercase">
          Access Intelligence
        </span>
      </span>
    </span>
  )
}
