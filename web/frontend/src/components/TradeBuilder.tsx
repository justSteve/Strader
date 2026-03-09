import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { api } from '../api/client';
import type { TradeAnalysis } from '../types';

const S: Record<string, React.CSSProperties> = {
  wrap: { padding: 12 },
  tabs: { display: 'flex', gap: 4, marginBottom: 12 },
  tab: { padding: '6px 16px', background: '#111118', border: '1px solid #1e1e2e', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#888' },
  tabActive: { padding: '6px 16px', background: '#7c4dff', border: '1px solid #7c4dff', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#fff' },
  form: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginBottom: 12 },
  field: { display: 'flex', flexDirection: 'column' as const, gap: 2 },
  label: { fontSize: 9, color: '#666', textTransform: 'uppercase' as const, letterSpacing: 1 },
  input: { background: '#1a1a2e', color: '#e0e0e0', border: '1px solid #333', padding: '6px 8px', borderRadius: 4, fontSize: 12 },
  btn: { padding: '8px 20px', background: '#7c4dff', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  results: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, marginBottom: 12 },
  card: { background: '#111118', border: '1px solid #1e1e2e', borderRadius: 6, padding: '8px 12px' },
  cardLabel: { fontSize: 9, color: '#666', textTransform: 'uppercase' as const },
  cardVal: { fontSize: 16, fontWeight: 700, marginTop: 2 },
  legs: { marginBottom: 12, fontSize: 11 },
  legRow: { display: 'flex', gap: 12, padding: '4px 0', borderBottom: '1px solid #1a1a2a' },
};

export function TradeBuilder() {
  const [mode, setMode] = useState<'butterfly' | 'vertical'>('butterfly');
  const [analysis, setAnalysis] = useState<TradeAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  // Butterfly params
  const [center, setCenter] = useState(5800);
  const [width, setWidth] = useState(10);
  const [qty, setQty] = useState(1);
  const [exp, setExp] = useState(new Date(Date.now() + 86400000).toISOString().slice(0, 10));

  // Vertical params
  const [longStrike, setLongStrike] = useState(5790);
  const [shortStrike, setShortStrike] = useState(5800);
  const [optType, setOptType] = useState('CALL');

  const analyze = async () => {
    setLoading(true);
    try {
      if (mode === 'butterfly') {
        const res = await api.trades.butterfly({ center_strike: center, width, quantity: qty, expiration: exp + 'T20:00:00Z', spot: 5800, iv: 0.18 });
        setAnalysis(res as TradeAnalysis);
      } else {
        const res = await api.trades.vertical({ long_strike: longStrike, short_strike: shortStrike, option_type: optType, quantity: qty, expiration: exp + 'T20:00:00Z', spot: 5800, iv: 0.18 });
        setAnalysis(res as TradeAnalysis);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={S.wrap}>
      <div style={S.tabs}>
        <button style={mode === 'butterfly' ? S.tabActive : S.tab} onClick={() => setMode('butterfly')}>Butterfly</button>
        <button style={mode === 'vertical' ? S.tabActive : S.tab} onClick={() => setMode('vertical')}>Vertical</button>
      </div>

      <div style={S.form}>
        {mode === 'butterfly' ? (
          <>
            <div style={S.field}>
              <span style={S.label}>Center Strike</span>
              <input style={S.input} type="number" value={center} onChange={(e) => setCenter(+e.target.value)} step={5} />
            </div>
            <div style={S.field}>
              <span style={S.label}>Wing Width</span>
              <input style={S.input} type="number" value={width} onChange={(e) => setWidth(+e.target.value)} step={5} />
            </div>
          </>
        ) : (
          <>
            <div style={S.field}>
              <span style={S.label}>Long Strike</span>
              <input style={S.input} type="number" value={longStrike} onChange={(e) => setLongStrike(+e.target.value)} step={5} />
            </div>
            <div style={S.field}>
              <span style={S.label}>Short Strike</span>
              <input style={S.input} type="number" value={shortStrike} onChange={(e) => setShortStrike(+e.target.value)} step={5} />
            </div>
            <div style={S.field}>
              <span style={S.label}>Type</span>
              <select style={S.input} value={optType} onChange={(e) => setOptType(e.target.value)}>
                <option value="CALL">Call</option>
                <option value="PUT">Put</option>
              </select>
            </div>
          </>
        )}
        <div style={S.field}>
          <span style={S.label}>Quantity</span>
          <input style={S.input} type="number" value={qty} onChange={(e) => setQty(+e.target.value)} min={1} />
        </div>
        <div style={S.field}>
          <span style={S.label}>Expiration</span>
          <input style={S.input} type="date" value={exp} onChange={(e) => setExp(e.target.value)} />
        </div>
        <div style={{ ...S.field, justifyContent: 'flex-end' }}>
          <button style={S.btn} onClick={analyze} disabled={loading}>{loading ? '...' : 'Analyze'}</button>
        </div>
      </div>

      {analysis && (
        <>
          <div style={S.legs}>
            {analysis.legs.map((leg, i) => (
              <div key={i} style={S.legRow}>
                <span style={{ color: leg.action === 'BUY' ? '#00e676' : '#ff1744', fontWeight: 600 }}>{leg.action}</span>
                <span>{leg.quantity}x</span>
                <span>{leg.type} {leg.strike}</span>
              </div>
            ))}
          </div>

          <div style={S.results}>
            <div style={S.card}>
              <div style={S.cardLabel}>Net Debit</div>
              <div style={S.cardVal}>${analysis.net_debit.toFixed(2)}</div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>Max Profit</div>
              <div style={{ ...S.cardVal, color: '#00e676' }}>${analysis.max_profit.toFixed(2)}</div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>Max Loss</div>
              <div style={{ ...S.cardVal, color: '#ff1744' }}>${analysis.max_loss.toFixed(2)}</div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>Delta</div>
              <div style={S.cardVal}>{analysis.greeks.delta.toFixed(4)}</div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>Theta</div>
              <div style={S.cardVal}>{analysis.greeks.theta.toFixed(4)}</div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>DTE</div>
              <div style={S.cardVal}>{analysis.dte}</div>
            </div>
            {analysis.breakevens && (
              <div style={S.card}>
                <div style={S.cardLabel}>Breakevens</div>
                <div style={S.cardVal}>{analysis.breakevens.map((b) => b.toFixed(1)).join(' / ')}</div>
              </div>
            )}
          </div>

          <div style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={analysis.risk_graph}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                <XAxis dataKey="price" stroke="#555" tick={{ fontSize: 10 }} />
                <YAxis stroke="#555" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#111118', border: '1px solid #333', fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#444" />
                <Line type="monotone" dataKey="pnl" stroke="#7c4dff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
