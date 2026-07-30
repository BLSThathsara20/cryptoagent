import { useState } from 'react';
import { fetchAPI, formatPrice } from '../api';
import { usePolling } from '../hooks/useLive';

export default function TradeFeed({ symbol = 'BTC' }) {
  const [trades, setTrades] = useState([]);

  usePolling(async () => {
    setTrades(await fetchAPI(`/market/trades/${symbol}?limit=30`));
  }, 3000, [symbol]);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Live Trades — {symbol}</h3>
      <div className="max-h-64 overflow-y-auto space-y-0.5">
        {trades.map((t, i) => (
          <div key={i} className="flex justify-between text-xs py-0.5 border-b border-dark-700/50">
            <span className={t.side === 'buy' ? 'text-accent-green' : 'text-accent-red'}>
              {t.side.toUpperCase()}
            </span>
            <span className="text-gray-300">{formatPrice(t.price)}</span>
            <span className="text-gray-500">{t.quantity?.toFixed(4)}</span>
            <span className="text-gray-600">
              {t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : ''}
            </span>
          </div>
        ))}
        {trades.length === 0 && (
          <p className="text-gray-500 text-xs text-center py-4">Waiting for trade data...</p>
        )}
      </div>
    </div>
  );
}
