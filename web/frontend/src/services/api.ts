const BASE = '/api';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  // Market
  getMarketContext: () => fetchJSON('/market/context'),

  // Options
  getOptionsChain: (symbol = '$SPX', expiration?: string, strikeCount = 25) => {
    const params = new URLSearchParams({ symbol, strike_count: String(strikeCount) });
    if (expiration) params.set('expiration', expiration);
    return fetchJSON(`/options/chain?${params}`);
  },
  getExpirations: (symbol = '$SPX') =>
    fetchJSON<string[]>(`/options/expirations?symbol=${symbol}`),

  // Positions
  getPositions: () => fetchJSON('/positions/'),
  getPortfolioGreeks: () => fetchJSON('/positions/greeks'),
  getAccountBalance: () => fetchJSON('/positions/balance'),

  // Trades
  previewButterfly: (order: {
    center_strike: number;
    wing_width: number;
    expiration: string;
    option_type: string;
    quantity: number;
  }) => fetchJSON('/trades/butterfly/preview', { method: 'POST', body: JSON.stringify(order) }),

  previewVertical: (order: {
    long_strike: number;
    short_strike: number;
    expiration: string;
    option_type: string;
    quantity: number;
  }) => fetchJSON('/trades/vertical/preview', { method: 'POST', body: JSON.stringify(order) }),

  // Risk
  getRiskStatus: () => fetchJSON('/risk/status'),

  // PnL
  getDailyPnL: (days = 30) => fetchJSON(`/pnl/daily?days=${days}`),
  getIntradayPnL: () => fetchJSON('/pnl/intraday'),

  // Health
  health: () => fetchJSON('/health'),
};
