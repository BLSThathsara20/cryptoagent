import AgentPanel from '../components/AgentPanel';
import FundManagerPanel from '../components/FundManagerPanel';
import TradeHistory from '../components/TradeHistory';

export default function Agent() {
  return (
    <div className="p-4 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-bold mb-2">AI Agents</h1>
      <p className="text-sm text-gray-500 mb-6">
        Fund Manager handles your capital · Trading Agent finds and executes trades
      </p>

      <div className="mb-6">
        <FundManagerPanel />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1">
          <AgentPanel />
        </div>
        <div className="lg:col-span-2">
          <TradeHistory />
        </div>
      </div>
    </div>
  );
}
