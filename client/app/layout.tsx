import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";

// Space Grotesk: technical, geometric headings. IBM Plex Sans: legible UI text.
// JetBrains Mono: IPs, timestamps and resource paths in the log tables.
const heading = Space_Grotesk({ subsets: ["latin"], variable: "--font-heading" });
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "Lognexa", template: "%s · Lognexa" },
  description: "AI-driven access log auditing and anomaly detection dashboard (student prototype).",
  icons: { icon: "/logo.jpg" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn("h-full", "antialiased", "font-sans", heading.variable, sans.variable, mono.variable)}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <TooltipProvider>
            <Toaster>
              <AppShell>{children}</AppShell>
            </Toaster>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
