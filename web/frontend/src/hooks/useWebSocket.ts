import { useEffect } from 'react';
import { wsService } from '../services/websocket';
import { useStore } from '../store';

export function useWebSocket() {
  const { setMarket, setPositions, setGreeks, setAlerts } = useStore();

  useEffect(() => {
    wsService.connect();

    const unsub = wsService.subscribe((channel, data) => {
      switch (channel) {
        case 'market':
          setMarket(data);
          break;
        case 'positions':
          setPositions(data);
          break;
        case 'greeks':
          setGreeks(data);
          break;
        case 'alerts':
          setAlerts(data);
          break;
      }
    });

    return () => {
      unsub();
      wsService.disconnect();
    };
  }, []);
}
