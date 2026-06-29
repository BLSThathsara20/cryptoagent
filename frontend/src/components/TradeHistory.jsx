import { useState, useEffect, useRef } from 'react';
import { fetchAPI, formatPrice } from '../api';

export default function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState(null);
  const [pnlHistory, setPnlHistory] = useState([]);
  const chartRef = useRef(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [t, s, p] = await Promise.all([
          fetchAPI('/trades/history?limit=50'),
          fetchAPI('/trades/stats'),
          fetchAPI('/agent/pnl-history'),
        ]);
        setTrades(t);
        setStats(s);
        setPnlHistory(p);
      } catch (e) {
        console.error(e);
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  // Simple SVG P&L chart
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
        <polyline
          fill="none"
          stroke="#3b82f6"
          strokeWidth="2"
          points={points}
        />
      </svg>
    );
  };

  return (
    <div className="space-y-4">
      {stats && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Total', value: stats.total },
            { label: 'Pending', value: stats.pending },
            { label: 'Wins', value: stats.wins, color: 'text-accent-green' },
            { label: 'Losses', value: stats.losses, color: 'text-accent-red' },
            { label: 'Total P&L', value: formatPrice(stats.total_pnl), color: stats.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red' },
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
        {renderPnLChart() || <p className="text-gray-500 text-xs text-center py-8">No P&L history yet</p>}
      </div>

      <div className="card overflow-hidden">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Trade History</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-dark-600 text-gray-400">
                <th className="px-2 py-2 text-left">Time</th>
                <th className="px-2 py-2 text-left">Coin</th>
                <th className="px-2 py-2 text-left">Dir</th>
                <th className="px-2 py-2 text-right">Entry</th>
                <th className="px-2 py-2 text-right">TP</th>
                <th className="px-2 py-2 text-right">SL</th>
                <th className="px-2 py-2 text-center">Conf</th>
                <th className="px-2 py-2 text-center">Status</th>
                <th className="px-2 py-2 text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-dark-700/50 hover:bg-dark-700/30">
                  <td className="px-2 py-1.5 text-gray-500">
                    {t.created_at ? new Date(t.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-medium">{t.coin}</td>
                  <td className="px-2 py-1.5">
                    <span className={t.direction === 'long' ? 'badge-green' : 'badge-red'}>
                      {t.direction}
                    </span>
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
                      {t.status}
                    </span>
                  </td>
                  <td className={`px-2 py-1.5 text-right ${(t.outcome_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    {t.outcome_pnl != null ? formatPrice(t.outcome_pnl) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
