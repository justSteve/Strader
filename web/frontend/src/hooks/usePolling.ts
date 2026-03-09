import { useEffect } from 'react';
import { api } from '../services/api';
import { useStore } from '../store';

export function usePolling(intervalMs = 5000) {
  const {
    setMarket, setChain, setPositions, setGreeks,
    setAlerts, setTodayPnl, setPnlHistory, selectedExpiration,
  } = useStore();

  useEffect(() => {
    let mounted = true;

    async function poll() {
      if (!mounted) return;

      try {
        const [market, chain, positions, greeks, alerts, todayPnl, pnlHistory] =
          await Promise.allSettled([
            api.market.context(),
            api.options.chain({ expiration: selectedExpiration || undefined }),
            api.positions.list(),
            api.positions.greeks(),
            api.risk.alerts(),
            api.pnl.today(),
            api.pnl.history(),
          ]);

        if (!mounted) return;

        if (market.status === 'fulfilled') setMarket(market.value);
        if (chain.status === 'fulfilled') setChain(chain.value);
        if (positions.status === 'fulfilled') setPositions(positions.value);
        if (greeks.status === 'fulfilled') setGreeks(greeks.value);
        if (alerts.status === 'fulfilled') setAlerts(alerts.value);
        if (todayPnl.status === 'fulfilled') setTodayPnl(todayPnl.value);
        if (pnlHistory.status === 'fulfilled') setPnlHistory(pnlHistory.value);
      } catch {
        // Silently handle polling errors
      }
    }

    poll();
    const timer = setInterval(poll, intervalMs);
    return () => { mounted = false; clearInterval(timer); };
  }, [intervalMs, selectedExpiration]);
}
