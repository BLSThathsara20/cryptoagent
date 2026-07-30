import { useState } from 'react';
import PriceTicker from '../components/PriceTicker';
import MarketTable from '../components/MarketTable';
import CandlestickChart from '../components/CandlestickChart';
import OrderBook from '../components/OrderBook';
import TradeFeed from '../components/TradeFeed';
import LiquidationTable from '../components/LiquidationTable';
import LongShortRatio from '../components/LongShortRatio';
import DominanceGauge from '../components/DominanceGauge';
import FearGreedIndex from '../components/FearGreedIndex';
import DecisionGlowBanner from '../components/DecisionGlowBanner';

const COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP'];

export default function Dashboard() {
  const [selectedCoin, setSelectedCoin] = useState('BTC');

  return (
    <div>
      <DecisionGlowBanner />
      <PriceTicker />

      <div className="p-4 space-y-4 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <FearGreedIndex />
          <DominanceGauge />
          <LongShortRatio />
        </div>

        <div className="flex gap-2 flex-wrap">
          {COINS.map((coin) => (
            <button
              key={coin}
              onClick={() => setSelectedCoin(coin)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                selectedCoin === coin
                  ? 'bg-accent-blue text-white'
                  : 'bg-dark-700 text-gray-400 hover:text-white'
              }`}
            >
              {coin}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <CandlestickChart symbol={selectedCoin} />
          </div>
          <div className="space-y-4">
            <OrderBook symbol={selectedCoin} />
            <TradeFeed symbol={selectedCoin} />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <MarketTable onSelectCoin={setSelectedCoin} />
          <LiquidationTable />
        </div>
      </div>
    </div>
  );
}
