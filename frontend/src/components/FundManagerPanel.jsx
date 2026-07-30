import { useState } from 'react';
import { fetchAPI, formatPrice, formatNumber } from '../api';
import { usePolling } from '../hooks/useLive';

const ACTION_COLORS = {
  hold: 'text-gray-300 bg-dark-700',
  deploy: 'text-accent-green bg-green-900/30',
  reduce: 'text-accent-red bg-red-900/30',
  reserve: 'text-accent-yellow bg-yellow-900/30',
  rebalance: 'text-accent-blue bg-blue-900/30',
};

export default function FundManagerPanel() {
  const [holdings, setHoldings] = useState(null);
  const [decision, setDecision] = useState(null);
  const [history, setHistory] = useState([]);

  usePolling(async () => {
    const [h, d, hist] = await Promise.all([
      fetchAPI('/portfolio/holdings'),
      fetchAPI('/portfolio/fund-manager/latest'),
      fetchAPI('/portfolio/fund-manager/history?limit=5'),
    ]);
    setHoldings(h);
    setDecision(d);
    setHistory(hist);
  }, 8000);

  if (!holdings) {
    return <div className="card text-gray-500 text-sm">Loading fund manager...</div>;
  }

  const total = holdings.total_usd || 1;
  const stablePct = (holdings.stable_usd / total * 100).toFixed(1);
  const cryptoPct = (holdings.crypto_usd / total * 100).toFixed(1);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-300">Fund Manager Agent</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Runs every agent cycle · Trades: {holdings.trading_mode === 'live' ? 'LIVE' : 'PAPER (mock)'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {holdings.binance_connected ? (
              <span className="badge-green text-xs">Binance Connected</span>
            ) : holdings.binance_market_ok ? (
              <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/30 text-accent-yellow">Market OK · account offline</span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/30 text-accent-yellow">Binance unreachable</span>
            )}
            {holdings.trading_mode === 'paper' && (
              <span className="text-xs px-2 py-0.5 rounded bg-blue-900/30 text-accent-blue">Paper Trading</span>
            )}
          </div>
        </div>

        {/* Portfolio summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="bg-dark-700/50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Total Portfolio</div>
            <div className="text-lg font-bold">{formatPrice(holdings.total_usd)}</div>
          </div>
          <div className="bg-dark-700/50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Available (Stables)</div>
            <div className="text-lg font-bold text-accent-green">{formatPrice(holdings.available_usd)}</div>
          </div>
          <div className="bg-dark-700/50 rounded-lg p-3">
            <div className="text-xs text-gray-500">In Crypto / Trades</div>
            <div className="text-lg font-bold">{formatPrice(holdings.crypto_usd)}</div>
          </div>
          <div className="bg-dark-700/50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Daily Target</div>
            <div className="text-lg font-bold text-accent-blue">
              {formatPrice(holdings.total_usd * holdings.daily_profit_target_percent / 100)}
            </div>
            <div className="text-[10px] text-gray-600">{holdings.daily_profit_target_percent}% / day</div>
          </div>
        </div>

        {/* Allocation bar */}
        <div className="mb-2">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Stables {stablePct}% (reserve target {holdings.reserve_percent}%)</span>
            <span>Crypto {cryptoPct}%</span>
          </div>
          <div className="flex h-3 rounded-full overflow-hidden">
            <div className="bg-accent-green" style={{ width: `${stablePct}%` }} />
            <div className="bg-accent-blue" style={{ width: `${cryptoPct}%` }} />
          </div>
        </div>
      </div>

      {/* Holdings table */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Where Your Funds Are</h3>
        <div className="overflow-x-auto max-h-48 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-dark-600 text-gray-400">
                <th className="text-left py-1.5 px-2">Asset</th>
                <th className="text-right py-1.5 px-2">Amount</th>
                <th className="text-right py-1.5 px-2">USD Value</th>
                <th className="text-right py-1.5 px-2">%</th>
                <th className="text-left py-1.5 px-2">Type</th>
              </tr>
            </thead>
            <tbody>
              {holdings.holdings?.map((h, i) => (
                <tr key={i} className="border-b border-dark-700/50">
                  <td className="py-1.5 px-2 font-medium">{h.asset}</td>
                  <td className="py-1.5 px-2 text-right text-gray-400">
                    {h.amount < 1 ? h.amount.toFixed(6) : formatNumber(h.amount)}
                  </td>
                  <td className="py-1.5 px-2 text-right">{formatPrice(h.usd_value)}</td>
                  <td className="py-1.5 px-2 text-right">{h.percent}%</td>
                  <td className="py-1.5 px-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      h.type === 'stable' ? 'bg-green-900/30 text-accent-green' :
                      h.type === 'open_trade' ? 'bg-blue-900/30 text-accent-blue' :
                      'bg-dark-600 text-gray-400'
                    }`}>
                      {h.type === 'open_trade' ? `${h.direction} trade` : h.type}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!holdings.binance_connected && (
          <p className="text-xs text-gray-600 mt-3">
            Add BINANCE_API_KEY + BINANCE_SECRET to .env to see your real Binance balances.
          </p>
        )}
        {holdings.binance_connected && holdings.trading_mode === 'paper' && (
          <p className="text-xs text-accent-green mt-3">
            ✓ Binance connected — viewing real balances. Trades are simulated (LIVE_MODE=false).
          </p>
        )}
      </div>

      {/* Latest fund manager decision */}
      {decision && (
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-semibold text-gray-300">Fund Manager Thinking</h3>
            <span className={`text-xs px-2 py-0.5 rounded uppercase font-medium ${ACTION_COLORS[decision.action] || ACTION_COLORS.hold}`}>
              {decision.action}
            </span>
          </div>
          {decision.asset && decision.amount_usd && (
            <p className="text-sm mb-2">
              <span className="text-gray-400">Action on </span>
              <span className="font-medium">{decision.asset}</span>
              <span className="text-gray-400"> · </span>
              <span className="text-accent-blue">{formatPrice(decision.amount_usd)}</span>
            </p>
          )}
          <p className="text-xs text-gray-400 leading-relaxed">{decision.reasoning}</p>
          <p className="text-[10px] text-gray-600 mt-2">
            {decision.created_at ? new Date(decision.created_at).toLocaleString() : ''}
          </p>
        </div>
      )}

      {/* Recent decisions */}
      {history.length > 1 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Recent Fund Decisions</h3>
          <div className="space-y-2">
            {history.slice(1, 5).map((d) => (
              <div key={d.id} className="text-xs border-l-2 border-dark-600 pl-2 py-1">
                <span className={`uppercase font-medium ${ACTION_COLORS[d.action]?.split(' ')[0] || ''}`}>
                  {d.action}
                </span>
                <span className="text-gray-500 ml-2">{d.reasoning?.slice(0, 80)}...</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
