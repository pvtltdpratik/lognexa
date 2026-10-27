import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { nf } from "@/lib/format"

export function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onPage: (p: number) => void
}) {
  if (total === 0) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  const go = (p: number) => (e: React.MouseEvent) => {
    e.preventDefault()
    if (p >= 1 && p <= pages) onPage(p)
  }
  return (
    <div className="flex flex-col items-center justify-between gap-2 sm:flex-row">
      <p className="tabular text-xs text-muted-foreground">
        Showing {nf.format(from)}–{nf.format(to)} of {nf.format(total)} · page {page} of {pages}
      </p>
      <Pagination className="mx-0 w-auto">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious href="#" onClick={go(page - 1)} aria-disabled={page <= 1} className={page <= 1 ? "pointer-events-none opacity-40" : ""} />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext href="#" onClick={go(page + 1)} aria-disabled={page >= pages} className={page >= pages ? "pointer-events-none opacity-40" : ""} />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  )
}
