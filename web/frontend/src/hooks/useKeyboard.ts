import { useEffect } from 'react';
import { useStore } from '../store';

const PANEL_KEYS: Record<string, string> = {
  '1': 'chain',
  '2': 'positions',
  '3': 'builder',
  '4': 'pnl',
};

export function useKeyboard() {
  const setActivePanel = useStore(s => s.setActivePanel);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Alt+number to switch panels
      if (e.altKey && PANEL_KEYS[e.key]) {
        e.preventDefault();
        setActivePanel(PANEL_KEYS[e.key]);
      }
    }

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [setActivePanel]);
}
