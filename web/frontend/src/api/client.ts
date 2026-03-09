const BASE = '/api';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  market: {
    context: () => fetchJSON('/market/context'),
  },
  options: {
    chain: (params?: { expiration?: string; strike_range?: number }) => {
      const qs = new URLSearchParams();
      if (params?.expiration) qs.set('expiration', params.expiration);
      if (params?.strike_range) qs.set('strike_range', String(params.strike_range));
      const q = qs.toString();
      return fetchJSON(`/options/chain${q ? '?' + q : ''}`);
    },
    expirations: () => fetchJSON('/options/expirations'),
  },
  positions: {
    list: () => fetchJSON('/positions'),
    summary: () => fetchJSON('/positions/summary'),
    pnlHistory: (days = 30) => fetchJSON(`/positions/pnl/history?days=${days}`),
    intradayPnl: () => fetchJSON('/positions/pnl/intraday'),
  },
  trades: {
    butterfly: (data: unknown) =>
      fetchJSON('/trades/butterfly/analyze', { method: 'POST', body: JSON.stringify(data) }),
    vertical: (data: unknown) =>
      fetchJSON('/trades/vertical/analyze', { method: 'POST', body: JSON.stringify(data) }),
  },
  risk: {
    status: () => fetchJSON('/risk/status'),
    scenarios: () => fetchJSON('/risk/scenarios'),
    evaluateEntry: (data: unknown) =>
      fetchJSON('/risk/evaluate-entry', { method: 'POST', body: JSON.stringify(data) }),
    alerts: (limit = 50) => fetchJSON(`/risk/alerts?limit=${limit}`),
  },
};
