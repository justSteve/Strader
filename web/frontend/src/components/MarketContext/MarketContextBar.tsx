import { useStore } from '../../store';

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}

function pnlClass(n: number): string {
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}

export default function MarketContextBar() {
  const market = useStore(s => s.market);

  if (!market) {
    return (
      <div className="market-bar" style={{
        display: 'flex', alignItems: 'center', padding: '0 12px',
        background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border)',
        gap: '24px', fontSize: 'var(--font-size-sm)',
      }}>
        <span style={{ color: 'var(--text-muted)' }}>Connecting...</span>
      </div>
    );
  }

  const statusColor = market.market_status === 'open' ? 'var(--green)' :
    market.market_status === 'pre' || market.market_status === 'after' ? 'var(--yellow)' : 'var(--text-muted)';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', padding: '0 12px',
      background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border)',
      gap: '24px', fontSize: 'var(--font-size-sm)', height: '36px',
    }}>
      {/* SPX */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>SPX</span>
        <span style={{ fontWeight: 'bold', fontSize: 'var(--font-size-lg)' }}>
          {fmt(market.spx_price)}
        </span>
        <span className={pnlClass(market.spx_change)}>
          {market.spx_change > 0 ? '+' : ''}{fmt(market.spx_change)} ({market.spx_change > 0 ? '+' : ''}{fmt(market.spx_change_pct)}%)
        </span>
      </div>

      <div style={{ width: '1px', height: '20px', background: 'var(--border)' }} />

      {/* VIX */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>VIX</span>
        <span style={{ color: 'var(--purple)' }}>{fmt(market.vix)}</span>
        <span className={pnlClass(-market.vix_change)} style={{ fontSize: 'var(--font-size-xs)' }}>
          {market.vix_change > 0 ? '+' : ''}{fmt(market.vix_change)}
        </span>
      </div>

      <div style={{ width: '1px', height: '20px', background: 'var(--border)' }} />

      {/* Expected Move */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>EM</span>
        <span>{fmt(market.expected_move)} ({fmt(market.expected_move_pct)}%)</span>
      </div>

      <div style={{ flex: 1 }} />

      {/* Time to Close */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>CLOSE</span>
        <span>{market.time_to_close}</span>
      </div>

      {/* Market Status */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '4px',
        padding: '2px 8px', borderRadius: '3px',
        background: 'var(--bg-primary)',
      }}>
        <span style={{
          width: '6px', height: '6px', borderRadius: '50%',
          background: statusColor, display: 'inline-block',
        }} />
        <span style={{ color: statusColor, textTransform: 'uppercase', fontSize: 'var(--font-size-xs)' }}>
          {market.market_status}
        </span>
      </div>
    </div>
  );
}
