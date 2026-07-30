import { useState } from 'react';
import { fetchAPI, formatPrice } from '../api';
import { usePolling } from '../hooks/useLive';

const STATUS_STYLE = {
  hit: 'bg-green-900/30 text-accent-green border-accent-green/40',
  in_progress: 'bg-blue-900/30 text-accent-blue border-accent-blue/40',
  missed: 'bg-red-900/20 text-accent-red border-accent-red/30',
  no_trade: 'bg-dark-700 text-gray-400 border-dark-600',
};

export default function DailyTargetPanel() {
  const [data, setData] = useState(null);
  const [showHistory, setShowHistory] = useState(false);

  usePolling(async () => {
    const d = await fetchAPI('/analytics/daily-targets?days=30');
    setData(d);
  }, 5000);

  if (!data?.today) {
    return (
      <div className="card text-xs text-gray-500">Loading daily target…</div>
    );
  }

  const t = data.today;
  const progress = Math.min(100, t.progress_percent || 0);
  const statusLabel =
    t.status === 'hit' ? 'HIT' : t.status === 'in_progress' ? 'IN PROGRESS' : 'MISSED';

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-300">Daily Profit Target</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Target {formatPrice(data.target_usd)} ({data.target_percent}% of portfolio)
          </p>
        </div>
        <span className={`text-xs px-2 py-1 rounded border font-medium ${STATUS_STYLE[t.status] || STATUS_STYLE.in_progress}`}>
          {statusLabel}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm mb-3">
        <div>
          <div className="text-xs text-gray-500">Today P&L</div>
          <div className={`font-bold ${(t.pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
            {formatPrice(t.pnl)}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Remaining</div>
          <div className="font-medium text-white">
            {formatPrice(Math.max(0, data.target_usd - (t.pnl || 0)))}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Hit rate (30d)</div>
          <div className="font-medium text-white">{data.stats?.hit_rate_percent ?? 0}%</div>
        </div>
      </div>

      <div className="h-2 bg-dark-700 rounded-full overflow-hidden mb-2">
        <div
          className={`h-full transition-all duration-500 ${t.hit ? 'bg-accent-green' : 'bg-accent-blue'}`}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="flex justify-between text-[11px] text-gray-500 mb-3">
        <span>{progress}% of target</span>
        <span>{t.trades} closed · {t.wins}W / {t.losses}L</span>
      </div>

      <button
        type="button"
        onClick={() => setShowHistory((v) => !v)}
        className="text-xs text-accent-blue hover:underline"
      >
        {showHistory ? 'Hide history' : 'View daily history'}
      </button>

      {showHistory && (
        <div className="mt-3 max-h-56 overflow-y-auto border-t border-dark-600 pt-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left py-1">Date</th>
                <th className="text-right py-1">P&L</th>
                <th className="text-right py-1">Target</th>
                <th className="text-center py-1">Result</th>
              </tr>
            </thead>
            <tbody>
              {(data.history || []).map((row) => (
                <tr key={row.date} className="border-t border-dark-700/50">
                  <td className="py-1.5 text-gray-300">
                    {row.date}{row.is_today ? ' (today)' : ''}
                  </td>
                  <td className={`py-1.5 text-right ${(row.pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    {formatPrice(row.pnl)}
                  </td>
                  <td className="py-1.5 text-right text-gray-400">{formatPrice(row.target_usd)}</td>
                  <td className="py-1.5 text-center">
                    <span className={`px-1.5 py-0.5 rounded ${STATUS_STYLE[row.status] || ''}`}>
                      {row.status === 'hit' ? 'HIT' : row.status === 'in_progress' ? '…' : row.status === 'no_trade' ? '—' : 'MISS'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
