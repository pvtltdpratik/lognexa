"use client"

import { MoonIcon, SunIcon } from "lucide-react"
import { ThemeProvider as NextThemesProvider, useTheme } from "next-themes"
import * as React from "react"

import { Button } from "@/components/ui/button"

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      {children}
    </NextThemesProvider>
  )
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme !== "light"
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      <SunIcon className="hidden dark:block" />
      <MoonIcon className="dark:hidden" />
    </Button>
  )
}
