import { createContext, useContext, useEffect, useState } from 'react';
import { fetchAPI, postAPI } from './api';
import {
  useNow,
  usePolling,
  formatCountdown,
  secondsUntil,
  isAgentBusy,
} from './hooks/useLive';

const LivePulseContext = createContext({
  pulse: null,
  prices: [],
  now: Date.now(),
  nextIn: null,
  lastPulseAt: null,
  formatCountdown,
});

/**
 * Global live state — React re-renders (Virtual DOM) every second for the clock,
 * and every few seconds when API data changes. No browser page refresh needed.
 */
export function LivePulseProvider({ children }) {
  const [pulse, setPulse] = useState(null);
  const [prices, setPrices] = useState([]);
  const [lastPulseAt, setLastPulseAt] = useState(null);
  const [missedPulses, setMissedPulses] = useState(0);
  const now = useNow(1000);

  const refreshPulse = async () => {
    try {
      const p = await fetchAPI('/system/pulse', 6000);
      setPulse(p);
      setLastPulseAt(Date.now());
      setMissedPulses(0);
    } catch {
      setMissedPulses((n) => n + 1);
    }
  };

  usePolling(refreshPulse, 2000);

  usePolling(async () => {
    const list = await fetchAPI('/market/prices?limit=20', 6000);
    if (Array.isArray(list)) setPrices(list);
  }, 4000);

  // When browser comes back online — recover backend services + refresh UI
  useEffect(() => {
    const onOnline = async () => {
      try {
        await postAPI('/system/recover', {}, 20000);
      } catch {
        /* recovery is best-effort; autopilot also runs every 2m */
      }
      await refreshPulse();
      try {
        const list = await fetchAPI('/market/prices?limit=20', 6000);
        if (Array.isArray(list)) setPrices(list);
      } catch {
        /* ignore */
      }
    };
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, []);

  // If several pulse polls fail, mark UI offline instead of showing stale LIVE
  const displayPulse =
    missedPulses >= 3 && pulse
      ? { ...pulse, online: false, network: 'offline', using_cached_data: true }
      : pulse;

  const agent = displayPulse?.agent;
  let nextIn = null;
  if (agent?.loop_running) {
    if (isAgentBusy(agent.stage)) {
      nextIn = 0;
    } else if (agent.next_run_at) {
      nextIn = secondsUntil(agent.next_run_at, now);
    } else if (agent.last_run_at && agent.interval_sec) {
      nextIn = secondsUntil(
        new Date(new Date(agent.last_run_at).getTime() + agent.interval_sec * 1000).toISOString(),
        now
      );
    } else if (agent.next_run_in_sec != null) {
      const elapsed = lastPulseAt ? Math.floor((now - lastPulseAt) / 1000) : 0;
      nextIn = Math.max(0, agent.next_run_in_sec - elapsed);
    }
  }

  return (
    <LivePulseContext.Provider
      value={{ pulse: displayPulse, prices, now, nextIn, lastPulseAt, formatCountdown }}
    >
      {children}
    </LivePulseContext.Provider>
  );
}

export function useLivePulse() {
  return useContext(LivePulseContext);
}
