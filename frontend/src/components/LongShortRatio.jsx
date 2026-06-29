import { useState, useEffect } from 'react';
import { fetchAPI } from '../api';

export default function LongShortRatio() {
  const [ratios, setRatios] = useState([]);

  useEffect(() => {
    const load = () => fetchAPI('/market/long-short').then(setRatios).catch(console.error);
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Long / Short Ratios</h3>
      <div className="space-y-3">
        {ratios.map((r) => {
          const longPct = (r.long_ratio || 0) * 100;
          const shortPct = (r.short_ratio || 0) * 100;
          return (
            <div key={r.symbol}>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium">{r.symbol}</span>
                <span className="text-gray-500">
                  OI: {r.open_interest ? `$${(r.open_interest / 1e6).toFixed(1)}M` : '—'}
                </span>
              </div>
              <div className="flex h-4 rounded overflow-hidden">
                <div
                  className="bg-accent-green flex items-center justify-center text-[10px] font-medium"
                  style={{ width: `${longPct || 50}%` }}
                >
                  {longPct ? `${longPct.toFixed(0)}% L` : ''}
                </div>
                <div
                  className="bg-accent-red flex items-center justify-center text-[10px] font-medium"
                  style={{ width: `${shortPct || 50}%` }}
                >
                  {shortPct ? `${shortPct.toFixed(0)}% S` : ''}
                </div>
              </div>
            </div>
          );
        })}
        {ratios.length === 0 && (
          <p className="text-gray-500 text-xs text-center py-4">No ratio data yet</p>
        )}
      </div>
    </div>
  );
}
