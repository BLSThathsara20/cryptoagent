import { useState, useEffect } from 'react';
import { fetchAPI } from '../api';

const COLORS = {
  'Extreme Fear': '#ef4444',
  Fear: '#f97316',
  Neutral: '#6b7280',
  Greed: '#84cc16',
  'Extreme Greed': '#10b981',
};

export default function FearGreedIndex() {
  const [data, setData] = useState({ value: 50, classification: 'Neutral' });

  useEffect(() => {
    const load = () => fetchAPI('/market/fear-greed').then(setData).catch(console.error);
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  const color = COLORS[data.classification] || '#6b7280';

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Fear & Greed Index</h3>
      <div className="text-center">
        <div className="text-4xl font-bold" style={{ color }}>{data.value}</div>
        <div className="text-sm mt-1" style={{ color }}>{data.classification}</div>
        <div className="mt-3 h-2 rounded-full bg-dark-600 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${data.value}%`, backgroundColor: color }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-gray-500 mt-1">
          <span>Extreme Fear</span>
          <span>Extreme Greed</span>
        </div>
      </div>
    </div>
  );
}
