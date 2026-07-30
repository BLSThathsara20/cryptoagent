import { useState } from 'react';
import { formatPrice, formatPercent, formatNumber } from '../api';
import { useLivePulse } from '../LivePulseContext';

export default function MarketTable({ onSelectCoin }) {
  const { prices: coins } = useLivePulse();
  const [sortBy, setSortBy] = useState('rank');
  const [sortDir, setSortDir] = useState('asc');

  const handleSort = (field) => {
    if (sortBy === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortBy(field); setSortDir('desc'); }
  };

  const sorted = [...coins].sort((a, b) => {
    const aVal = a[sortBy] ?? 0;
    const bVal = b[sortBy] ?? 0;
    return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
  });

  const SortHeader = ({ field, children }) => (
    <th
      className="px-3 py-2 text-left text-xs text-gray-400 cursor-pointer hover:text-white"
      onClick={() => handleSort(field)}
    >
      {children} {sortBy === field && (sortDir === 'asc' ? '↑' : '↓')}
    </th>
  );

  return (
    <div className="card overflow-hidden">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Market Overview</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-dark-600">
              <SortHeader field="rank">#</SortHeader>
              <th className="px-3 py-2 text-left text-xs text-gray-400">Coin</th>
              <SortHeader field="price">Price</SortHeader>
              <SortHeader field="change_24h">24h %</SortHeader>
              <SortHeader field="volume_24h">Volume</SortHeader>
              <SortHeader field="market_cap">Market Cap</SortHeader>
            </tr>
          </thead>
          <tbody>
            {sorted.map((coin) => (
              <tr
                key={coin.symbol}
                className="border-b border-dark-700 hover:bg-dark-700/50 cursor-pointer transition-colors"
                onClick={() => onSelectCoin?.(coin.symbol)}
              >
                <td className="px-3 py-2 text-gray-500">{coin.rank}</td>
                <td className="px-3 py-2 font-medium">
                  <span className="text-white">{coin.symbol}</span>
                  <span className="text-gray-500 text-xs ml-1">{coin.name}</span>
                </td>
                <td className="px-3 py-2">{formatPrice(coin.price)}</td>
                <td className={`px-3 py-2 ${coin.change_24h >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                  {formatPercent(coin.change_24h)}
                </td>
                <td className="px-3 py-2 text-gray-300">{formatNumber(coin.volume_24h)}</td>
                <td className="px-3 py-2 text-gray-300">{formatNumber(coin.market_cap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
