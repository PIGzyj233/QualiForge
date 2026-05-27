import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

type PaginationProps = {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  itemsPerPage?: number;
};

export function Pagination({ currentPage, totalPages, totalItems, onPageChange, itemsPerPage = 10 }: PaginationProps) {
  if (totalItems === 0) return null;
  const start = (currentPage - 1) * itemsPerPage + 1;
  const end = Math.min(currentPage * itemsPerPage, totalItems);
  const pages = buildPageNumbers(currentPage, totalPages);

  return (
    <nav className="flex items-center justify-between gap-4 px-1 py-3 text-sm" aria-label="分页导航">
      <span className="text-xs text-[var(--muted-foreground)]">显示 {start}–{end}，共 {totalItems} 条</span>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon" className="h-7 w-7" disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} aria-label="上一页">
          <ChevronLeft size={14} />
        </Button>
        {pages.map((page, i) =>
          page === "ellipsis" ? (
            <span key={`e-${i}`} className="px-1 text-[var(--muted-foreground)]">…</span>
          ) : (
            <Button
              key={page}
              variant={page === currentPage ? "default" : "outline"}
              size="icon"
              className="h-7 w-7 text-xs"
              onClick={() => onPageChange(page)}
              aria-current={page === currentPage ? "page" : undefined}
            >
              {page}
            </Button>
          )
        )}
        <Button variant="outline" size="icon" className="h-7 w-7" disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)} aria-label="下一页">
          <ChevronRight size={14} />
        </Button>
      </div>
    </nav>
  );
}

function buildPageNumbers(current: number, total: number): Array<number | "ellipsis"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: Array<number | "ellipsis"> = [1];
  if (current > 3) pages.push("ellipsis");
  for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i);
  if (current < total - 2) pages.push("ellipsis");
  pages.push(total);
  return pages;
}
