const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  market: {
    context: () => fetchJson<import('../types').MarketContext>('/api/market/context'),
  },
  options: {
    chain: (params?: { symbol?: string; expiration?: string; strike_count?: number }) => {
      const qs = new URLSearchParams();
      if (params?.symbol) qs.set('symbol', params.symbol);
      if (params?.expiration) qs.set('expiration', params.expiration);
      if (params?.strike_count) qs.set('strike_count', String(params.strike_count));
      return fetchJson<import('../types').OptionsChain>(`/api/options/chain?${qs}`);
    },
  },
  positions: {
    list: () => fetchJson<import('../types').Position[]>('/api/positions/'),
    greeks: () => fetchJson<import('../types').PortfolioGreeks>('/api/positions/greeks'),
  },
  trades: {
    butterfly: (data: any) => fetchJson<import('../types').TradeSetup>('/api/trades/butterfly', {
      method: 'POST', body: JSON.stringify(data),
    }),
    vertical: (data: any) => fetchJson<import('../types').TradeSetup>('/api/trades/vertical', {
      method: 'POST', body: JSON.stringify(data),
    }),
    evaluate: (data: any) => fetchJson<import('../types').TradeEvaluation>('/api/trades/evaluate', {
      method: 'POST', body: JSON.stringify(data),
    }),
  },
  risk: {
    alerts: () => fetchJson<import('../types').RiskAlert[]>('/api/risk/alerts'),
  },
  pnl: {
    today: () => fetchJson<import('../types').PnLSummary>('/api/pnl/today'),
    history: (days?: number) => fetchJson<import('../types').PnLSummary[]>(`/api/pnl/history?days=${days || 30}`),
  },
};
