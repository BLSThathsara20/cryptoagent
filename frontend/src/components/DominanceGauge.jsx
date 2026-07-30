import { useState } from 'react';
import { fetchAPI } from '../api';
import { usePolling } from '../hooks/useLive';

export default function DominanceGauge() {
  const [data, setData] = useState({ btc_dominance: 0, eth_dominance: 0 });

  usePolling(async () => {
    setData(await fetchAPI('/market/dominance'));
  }, 15000);

  const Gauge = ({ label, value, color }) => (
    <div className="text-center">
      <div className="relative w-24 h-24 mx-auto">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" strokeWidth="3" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={color} strokeWidth="3"
            strokeDasharray={`${value || 0} 100`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-bold">{value?.toFixed(1) || '0'}%</span>
        </div>
      </div>
      <p className="text-xs text-gray-400 mt-1">{label}</p>
    </div>
  );

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Market Dominance</h3>
      <div className="flex justify-around">
        <Gauge label="BTC" value={data.btc_dominance} color="#f59e0b" />
        <Gauge label="ETH" value={data.eth_dominance} color="#3b82f6" />
      </div>
    </div>
  );
}
