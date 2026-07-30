import { useState } from 'react';
import { fetchAPI, formatPrice } from '../api';
import { usePolling } from '../hooks/useLive';

export default function OrderBook({ symbol = 'BTC' }) {
  const [book, setBook] = useState({ bids: [], asks: [] });

  usePolling(async () => {
    setBook(await fetchAPI(`/market/orderbook/${symbol}`));
  }, 3000, [symbol]);

  const maxQty = Math.max(
    ...book.bids.map((b) => b.quantity),
    ...book.asks.map((a) => a.quantity),
    1
  );

  const Row = ({ entry, side }) => {
    const pct = (entry.quantity / maxQty) * 100;
    const bg = side === 'bid' ? 'bg-green-900/20' : 'bg-red-900/20';
    return (
      <div className={`relative flex justify-between px-2 py-0.5 text-xs ${bg}`}>
        <div
          className={`absolute inset-y-0 ${side === 'bid' ? 'right-0 bg-green-500/10' : 'left-0 bg-red-500/10'}`}
          style={{ width: `${pct}%` }}
        />
        <span className={side === 'bid' ? 'text-accent-green' : 'text-accent-red'}>
          {formatPrice(entry.price)}
        </span>
        <span className="text-gray-400">{entry.quantity.toFixed(4)}</span>
      </div>
    );
  };

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Order Book — {symbol}</h3>
      <div className="grid grid-cols-2 gap-2 max-h-80 overflow-y-auto">
        <div>
          <div className="text-xs text-accent-green mb-1 font-medium">Bids</div>
          {book.bids.slice(0, 15).map((b, i) => <Row key={i} entry={b} side="bid" />)}
        </div>
        <div>
          <div className="text-xs text-accent-red mb-1 font-medium">Asks</div>
          {book.asks.slice(0, 15).map((a, i) => <Row key={i} entry={a} side="ask" />)}
        </div>
      </div>
    </div>
  );
}
