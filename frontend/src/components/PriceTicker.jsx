import { useState, useEffect } from 'react';
import { fetchAPI, formatPrice, formatPercent } from '../api';

export default function PriceTicker() {
  const [coins, setCoins] = useState([]);

  useEffect(() => {
    const load = () => fetchAPI('/market/prices?limit=20').then(setCoins).catch(console.error);
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-dark-800 border-b border-dark-600 overflow-hidden">
      <div className="flex animate-scroll whitespace-nowrap py-2 px-4 gap-6">
        {coins.concat(coins).map((coin, i) => (
          <div key={`${coin.symbol}-${i}`} className="inline-flex items-center gap-2 text-sm">
            <span className="font-medium text-white">{coin.symbol}</span>
            <span className="text-gray-300">{formatPrice(coin.price)}</span>
            <span className={coin.change_24h >= 0 ? 'text-accent-green' : 'text-accent-red'}>
              {formatPercent(coin.change_24h)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
