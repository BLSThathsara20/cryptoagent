import { formatCountdown, isAgentBusy } from '../hooks/useLive';
import { useLivePulse } from '../LivePulseContext';

function formatAgo(iso, nowMs) {
  if (!iso) return 'never';
  const sec = Math.max(0, Math.floor((nowMs - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

/** Compact banner driven by LivePulse — updates every second without page refresh. */
export default function AgentRunningBanner() {
  const { pulse, now, nextIn } = useLivePulse();
  const agent = pulse?.agent;

  if (!agent) {
    return (
      <div className="bg-dark-800 border-b border-dark-600 px-4 py-2 text-xs text-gray-500">
        Checking agent…
      </div>
    );
  }

  const cycling = isAgentBusy(agent.stage);
  const loopOn = Boolean(agent.loop_running);
  const label = cycling
    ? `Agent working · ${agent.label || agent.stage}`
    : loopOn
      ? `Next cycle ${formatCountdown(nextIn)}`
      : 'Agent loop stopped';
  const color = !loopOn ? 'bg-accent-red' : cycling ? 'bg-accent-blue' : 'bg-accent-green';
  const pulseCls = loopOn ? 'animate-pulse' : '';

  return (
    <div className="bg-dark-800 border-b border-dark-600 px-4 py-2 flex flex-wrap items-center justify-between gap-2 text-sm">
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-2 font-medium text-white">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${color} ${pulseCls}`} />
          {label}
        </span>
        <span className="text-xs text-gray-500">
          Mode {agent.live_mode ? 'LIVE' : 'PAPER'} · every {agent.interval_sec}s · last cycle{' '}
          {formatAgo(agent.last_run_at, now)}
        </span>
      </div>
      <a href="/agent" className="text-xs text-accent-blue hover:underline">
        Agent panel →
      </a>
    </div>
  );
}
