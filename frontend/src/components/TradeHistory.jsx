import { useState } from 'react';
import { fetchAPI, formatPrice } from '../api';
import TradeDetailModal from './TradeDetailModal';
import PaginationBar from './PaginationBar';
import { usePolling } from '../hooks/useLive';

const PAGE_SIZE = 25;

export default function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0, page_size: PAGE_SIZE });
  const [stats, setStats] = useState(null);
  const [pnlHistory, setPnlHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(1);

  usePolling(async () => {
    const statusParam = filter === 'all' ? '' : `&status=${filter}`;
    const [hist, s, p] = await Promise.all([
      fetchAPI(`/trades/history?page=${page}&page_size=${PAGE_SIZE}${statusParam}`),
      fetchAPI('/trades/stats'),
      fetchAPI('/agent/pnl-history?limit=200'),
    ]);

    // API returns { trades, total, page, pages } — never assign the whole object to state
    const list = Array.isArray(hist)
      ? hist
      : Array.isArray(hist?.trades)
        ? hist.trades
        : [];
    setTrades(list);
    setMeta({
      page: Array.isArray(hist) ? 1 : (hist?.page || page),
      pages: Array.isArray(hist) ? 1 : (hist?.pages || 1),
      total: Array.isArray(hist) ? list.length : (hist?.total || list.length),
      page_size: Array.isArray(hist) ? PAGE_SIZE : (hist?.page_size || PAGE_SIZE),
    });
    setStats(s && typeof s === 'object' ? s : null);
    setPnlHistory(Array.isArray(p) ? p : []);
  }, 5000, [page, filter]);

  // Always render from an array (guards against stale HMR / bad payloads)
  const rows = Array.isArray(trades) ? trades : [];

  const changeFilter = (id) => {
    setFilter(id);
    setPage(1);
  };

  const openTrade = async (id) => {
    setLoadingDetail(true);
    try {
      const detail = await fetchAPI(`/trades/${id}`);
      setSelected(detail);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingDetail(false);
    }
  };

  const renderPnLChart = () => {
    if (pnlHistory.length < 2) return null;
    const balances = pnlHistory.map((p) => p.balance);
    const min = Math.min(...balances);
    const max = Math.max(...balances);
    const range = max - min || 1;
    const w = 600;
    const h = 120;
    const points = balances
      .map((b, i) => `${(i / (balances.length - 1)) * w},${h - ((b - min) / range) * h}`)
      .join(' ');

    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-28">
        <polyline fill="none" stroke="#3b82f6" strokeWidth="2" points={points} />
      </svg>
    );
  };

  const pnlCell = (t) => {
    if (t.status === 'pending') {
      if (t.unrealized_pnl != null) {
        return (
          <span className={(t.unrealized_pnl || 0) >= 0 ? 'text-accent-yellow' : 'text-accent-red'} title="Unrealized — trade still open">
            {formatPrice(t.unrealized_pnl)}
            <span className="text-[9px] text-gray-500 ml-1">open</span>
          </span>
        );
      }
      return <span className="text-gray-500" title="No result yet — waiting for TP/SL/time exit">— open</span>;
    }
    if (t.outcome_pnl != null) {
      return (
        <span className={(t.outcome_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>
          {formatPrice(t.outcome_pnl)}
        </span>
      );
    }
    return <span className="text-gray-500">—</span>;
  };

  return (
    <div className="space-y-4">
      {stats && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Total', value: stats.total },
            { label: 'Open', value: stats.pending, color: 'text-accent-yellow' },
            { label: 'Wins', value: stats.wins, color: 'text-accent-green' },
            { label: 'Losses', value: stats.losses, color: 'text-accent-red' },
            { label: 'Realized P&L', value: formatPrice(stats.total_pnl), color: stats.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red' },
          ].map((s) => (
            <div key={s.label} className="card text-center">
              <div className="text-xs text-gray-500">{s.label}</div>
              <div className={`text-lg font-bold ${s.color || ''}`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Paper Trading P&L</h3>
        {renderPnLChart() || <p className="text-gray-500 text-xs text-center py-8">No P&L history yet — appears when trades close</p>}
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-300">Trade History</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">
              Click a row for strategy, entry reason, and close details.
              Open trades show unrealized P&L until TP / SL / time-exit.
            </p>
          </div>
          <div className="flex gap-1">
            {[
              ['all', 'All'],
              ['pending', 'Open'],
              ['closed', 'Closed'],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => changeFilter(id)}
                className={`px-2.5 py-1 rounded text-[11px] ${
                  filter === id ? 'bg-accent-blue text-white' : 'text-gray-400 hover:bg-dark-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-dark-600 text-gray-400">
                <th className="px-2 py-2 text-left">Time</th>
                <th className="px-2 py-2 text-left">Coin</th>
                <th className="px-2 py-2 text-left">Dir</th>
                <th className="px-2 py-2 text-left hidden md:table-cell">Strategy</th>
                <th className="px-2 py-2 text-right">Entry</th>
                <th className="px-2 py-2 text-right">TP</th>
                <th className="px-2 py-2 text-right">SL</th>
                <th className="px-2 py-2 text-center">Conf</th>
                <th className="px-2 py-2 text-center">Status</th>
                <th className="px-2 py-2 text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => openTrade(t.id)}
                  className="border-b border-dark-700/50 hover:bg-dark-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-2 py-1.5 text-gray-500 whitespace-nowrap">
                    {t.created_at ? new Date(t.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-medium">{t.coin}</td>
                  <td className="px-2 py-1.5">
                    <span className={t.direction === 'long' ? 'badge-green' : 'badge-red'}>
                      {t.direction}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-gray-400 max-w-[140px] truncate hidden md:table-cell" title={t.strategy || ''}>
                    {t.strategy || '—'}
                  </td>
                  <td className="px-2 py-1.5 text-right">{formatPrice(t.entry_price)}</td>
                  <td className="px-2 py-1.5 text-right text-accent-green">{formatPrice(t.take_profit)}</td>
                  <td className="px-2 py-1.5 text-right text-accent-red">{formatPrice(t.stop_loss)}</td>
                  <td className="px-2 py-1.5 text-center">{t.confidence}</td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={
                      t.status === 'win' ? 'text-accent-green' :
                      t.status === 'loss' ? 'text-accent-red' : 'text-accent-yellow'
                    }>
                      {t.status === 'pending' ? 'open' : t.status}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right">{pnlCell(t)}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-gray-500">
                    No trades in this filter
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {loadingDetail && (
            <p className="text-xs text-gray-500 text-center py-2">Loading trade…</p>
          )}
        </div>
        <PaginationBar
          page={meta.page}
          pages={meta.pages}
          total={meta.total}
          pageSize={meta.page_size}
          onPageChange={setPage}
          label="trades"
        />
      </div>

      {selected && (
        <TradeDetailModal trade={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
