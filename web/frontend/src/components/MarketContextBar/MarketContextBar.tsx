import { useCallback } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import type { MarketContext } from '../../types'

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals)
}

function sign(n: number): string {
  return n >= 0 ? '+' : ''
}

export function MarketContextBar() {
  const fetcher = useCallback(() => api.getMarketContext() as Promise<MarketContext>, [])
  const { data: ctx } = usePolling(fetcher, 5000)

  if (!ctx) {
    return (
      <div style={styles.bar}>
        <span className="muted">Loading market data...</span>
      </div>
    )
  }

  return (
    <div style={styles.bar}>
      <div style={styles.group}>
        <span style={styles.label}>SPX</span>
        <span style={styles.price}>{fmt(ctx.spx_price)}</span>
        <span className={ctx.spx_change >= 0 ? 'positive' : 'negative'}>
          {sign(ctx.spx_change)}{fmt(ctx.spx_change)} ({sign(ctx.spx_change_pct)}{fmt(ctx.spx_change_pct)}%)
        </span>
      </div>

      <div style={styles.sep} />

      <div style={styles.group}>
        <span style={styles.label}>VIX</span>
        <span className="mono">{fmt(ctx.vix)}</span>
        <span className={ctx.vix_change <= 0 ? 'positive' : 'negative'}>
          {sign(ctx.vix_change)}{fmt(ctx.vix_change)}
        </span>
      </div>

      <div style={styles.sep} />

      <div style={styles.group}>
        <span style={styles.label}>EM</span>
        <span className="mono">{fmt(ctx.expected_move, 1)}</span>
        <span className="muted">({fmt(ctx.expected_move_pct)}%)</span>
      </div>

      <div style={styles.sep} />

      <div style={styles.group}>
        <span
          className={ctx.market_open ? 'positive' : 'negative'}
          style={{ fontWeight: 600 }}
        >
          {ctx.market_open ? 'OPEN' : 'CLOSED'}
        </span>
        {ctx.market_open && ctx.time_to_close && (
          <span className="muted">{ctx.time_to_close} to close</span>
        )}
      </div>

      <div style={{ flex: 1 }} />

      <div style={styles.group}>
        <span style={styles.brand}>STRADER</span>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '6px 16px',
    background: '#070b12',
    borderBottom: '1px solid var(--border)',
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    minHeight: 32,
  },
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  label: {
    color: 'var(--text-muted)',
    fontWeight: 600,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  price: {
    fontWeight: 700,
    fontSize: 14,
    color: 'var(--text-primary)',
  },
  sep: {
    width: 1,
    height: 16,
    background: 'var(--border)',
  },
  brand: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '2px',
    color: 'var(--blue)',
  },
}
