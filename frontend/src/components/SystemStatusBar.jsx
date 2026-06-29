import { useState, useEffect } from 'react';
import { fetchAPI } from '../api';

export default function SystemStatusBar() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const load = () =>
      fetchAPI('/system/status')
        .then((s) => setStatus(s))
        .catch(() => {});
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!status) return null;

  const healthy = status.health.status === 'healthy';

  return (
    <div className="bg-dark-800/80 border-b border-dark-600 px-4 py-1.5 flex items-center justify-between text-xs text-gray-500">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${healthy ? 'bg-accent-green' : 'bg-accent-red'}`} />
          System {healthy ? 'Healthy' : 'Degraded'}
        </span>
        <span>Agent: <span className="text-gray-300 capitalize">{status.agent.status}</span></span>
        <span>Mode: <span className="text-gray-300">{status.configuration.live_mode ? 'LIVE' : 'PAPER'}</span></span>
        <span className="hidden md:inline">Automation: <span className="text-accent-blue">{status.automation_level.percent}%</span></span>
      </div>
      <a href="/settings" className="text-accent-blue hover:underline">Settings →</a>
    </div>
  );
}
