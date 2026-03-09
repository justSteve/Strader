import { create } from 'zustand';
import type {
  MarketContext, OptionsChain, Position, PortfolioGreeks,
  RiskAlert, PnLSummary, TradeSetup, TradeEvaluation,
} from '../types';

interface AppState {
  // Market
  market: MarketContext | null;
  setMarket: (m: MarketContext) => void;

  // Options chain
  chain: OptionsChain | null;
  selectedExpiration: string | null;
  setChain: (c: OptionsChain) => void;
  setSelectedExpiration: (e: string) => void;

  // Positions
  positions: Position[];
  greeks: PortfolioGreeks | null;
  setPositions: (p: Position[]) => void;
  setGreeks: (g: PortfolioGreeks) => void;

  // Risk
  alerts: RiskAlert[];
  setAlerts: (a: RiskAlert[]) => void;

  // P&L
  todayPnl: PnLSummary | null;
  pnlHistory: PnLSummary[];
  setTodayPnl: (p: PnLSummary) => void;
  setPnlHistory: (h: PnLSummary[]) => void;

  // Trade builder
  currentSetup: TradeSetup | null;
  evaluation: TradeEvaluation | null;
  setCurrentSetup: (s: TradeSetup | null) => void;
  setEvaluation: (e: TradeEvaluation | null) => void;

  // UI
  activePanel: string;
  setActivePanel: (p: string) => void;
}

export const useStore = create<AppState>((set) => ({
  market: null,
  setMarket: (m) => set({ market: m }),

  chain: null,
  selectedExpiration: null,
  setChain: (c) => set({ chain: c }),
  setSelectedExpiration: (e) => set({ selectedExpiration: e }),

  positions: [],
  greeks: null,
  setPositions: (p) => set({ positions: p }),
  setGreeks: (g) => set({ greeks: g }),

  alerts: [],
  setAlerts: (a) => set({ alerts: a }),

  todayPnl: null,
  pnlHistory: [],
  setTodayPnl: (p) => set({ todayPnl: p }),
  setPnlHistory: (h) => set({ pnlHistory: h }),

  currentSetup: null,
  evaluation: null,
  setCurrentSetup: (s) => set({ currentSetup: s }),
  setEvaluation: (e) => set({ evaluation: e }),

  activePanel: 'chain',
  setActivePanel: (p) => set({ activePanel: p }),
}));
