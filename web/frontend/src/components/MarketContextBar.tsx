import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { MarketContext } from '../types';

const S: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex',
    gap: 24,
    padding: '8px 16px',
    background: '#111118',
    borderBottom: '1px solid #1e1e2e',
    fontSize: 13,
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  item: { display: 'flex', gap: 6, alignItems: 'center' },
  label: { color: '#666', textTransform: 'uppercase' as const, fontSize: 10, letterSpacing: 1 },
  val: { fontWeight: 600 },
  pos: { color: '#00e676' },
  neg: { color: '#ff1744' },
  logo: { fontWeight: 700, color: '#7c4dff', fontSize: 15, marginRight: 8 },
};

export function MarketContextBar() {
  const [ctx, setCtx] = useState<MarketContext | null>(null);

  useEffect(() => {
    const load = () => api.market.context().then((d) => setCtx(d as MarketContext));
    load();
    const iv = setInterval(load, 2000);
    return () => clearInterval(iv);
  }, []);

  if (!ctx) return <div style={S.bar}>Loading...</div>;

  const chgStyle = ctx.spx_change >= 0 ? S.pos : S.neg;

  return (
    <div style={S.bar}>
      <span style={S.logo}>STRADER</span>
      <div style={S.item}>
        <span style={S.label}>SPX</span>
        <span style={S.val}>{ctx.spx_price.toFixed(2)}</span>
        <span style={{ ...S.val, ...chgStyle }}>
          {ctx.spx_change >= 0 ? '+' : ''}{ctx.spx_change.toFixed(2)} ({ctx.spx_change_pct.toFixed(2)}%)
        </span>
      </div>
      <div style={S.item}>
        <span style={S.label}>VIX</span>
        <span style={S.val}>{ctx.vix.toFixed(2)}</span>
      </div>
      <div style={S.item}>
        <span style={S.label}>Exp Move</span>
        <span style={S.val}>{ctx.expected_move.toFixed(1)}</span>
      </div>
      <div style={S.item}>
        <span style={S.label}>Close</span>
        <span style={S.val}>{ctx.time_to_close}</span>
      </div>
    </div>
  );
}
