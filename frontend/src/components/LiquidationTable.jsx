import { useState, useEffect } from 'react';
import { fetchAPI, formatNumber } from '../api';

export default function LiquidationTable() {
  const [liquidations, setLiquidations] = useState([]);

  useEffect(() => {
    const load = () => fetchAPI('/market/liquidations?limit=20').then(setLiquidations).catch(console.error);
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Liquidations (24h)</h3>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-dark-600 text-gray-400">
              <th className="px-2 py-1 text-left">Coin</th>
              <th className="px-2 py-1 text-left">Side</th>
              <th className="px-2 py-1 text-right">Size (USD)</th>
              <th className="px-2 py-1 text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {liquidations.map((l, i) => (
              <tr key={i} className="border-b border-dark-700/50">
                <td className="px-2 py-1 font-medium">{l.symbol}</td>
                <td className="px-2 py-1">
                  <span className={l.side === 'long' ? 'badge-red' : 'badge-green'}>
                    {l.side}
                  </span>
                </td>
                <td className="px-2 py-1 text-right text-gray-300">${formatNumber(l.size)}</td>
                <td className="px-2 py-1 text-right text-gray-500">
                  {l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {liquidations.length === 0 && (
          <p className="text-gray-500 text-xs text-center py-4">No liquidation data yet</p>
        )}
      </div>
    </div>
  );
}
