/** Shared Prev / Next pagination control for growing lists. */
export default function PaginationBar({ page, pages, total, pageSize, onPageChange, label = 'items' }) {
  if (!total && total !== 0) return null;
  const safePages = Math.max(1, pages || 1);
  const safePage = Math.min(Math.max(1, page || 1), safePages);
  const from = total === 0 ? 0 : (safePage - 1) * (pageSize || 25) + 1;
  const to = Math.min(safePage * (pageSize || 25), total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 pt-3 mt-2 border-t border-dark-700 text-xs text-gray-500">
      <span>
        {total === 0 ? `No ${label}` : `Showing ${from}–${to} of ${total} ${label}`}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
          className="px-2.5 py-1 rounded bg-dark-700 text-gray-300 disabled:opacity-40 hover:bg-dark-600 disabled:hover:bg-dark-700"
        >
          Prev
        </button>
        <span className="tabular-nums text-gray-400">
          Page {safePage} / {safePages}
        </span>
        <button
          type="button"
          disabled={safePage >= safePages}
          onClick={() => onPageChange(safePage + 1)}
          className="px-2.5 py-1 rounded bg-dark-700 text-gray-300 disabled:opacity-40 hover:bg-dark-600 disabled:hover:bg-dark-700"
        >
          Next
        </button>
      </div>
    </div>
  );
}
