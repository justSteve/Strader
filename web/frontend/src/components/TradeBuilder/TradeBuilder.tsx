import { useState } from 'react';
import { useStore } from '../../store';
import { api } from '../../services/api';
import type { TradeEvaluation, RiskGraphPoint } from '../../types';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine,
} from 'recharts';

export default function TradeBuilder() {
  const chain = useStore(s => s.chain);
  const [strategy, setStrategy] = useState<'butterfly' | 'vertical'>('butterfly');
  const [optionType, setOptionType] = useState<'CALL' | 'PUT'>('CALL');
  const [centerStrike, setCenterStrike] = useState('');
  const [width, setWidth] = useState('5');
  const [longStrike, setLongStrike] = useState('');
  const [shortStrike, setShortStrike] = useState('');
  const [evaluation, setEvaluation] = useState<TradeEvaluation | null>(null);
  const [loading, setLoading] = useState(false);

  const expiration = useStore(s => s.selectedExpiration) || chain?.expirations[0] || '';

  async function buildAndEvaluate() {
    setLoading(true);
    try {
      let setup;
      if (strategy === 'butterfly') {
        setup = await api.trades.butterfly({
          center_strike: parseFloat(centerStrike),
          width: parseFloat(width),
          expiration,
          option_type: optionType,
        });
      } else {
        setup = await api.trades.vertical({
          long_strike: parseFloat(longStrike),
          short_strike: parseFloat(shortStrike),
          expiration,
          option_type: optionType,
        });
      }

      const eval_ = await api.trades.evaluate({
        setup,
        underlying_price: chain?.underlying_price || 5850,
      });
      setEvaluation(eval_);
    } catch (err) {
      console.error('Trade build failed:', err);
    }
    setLoading(false);
  }

  return (
    <div className="panel" style={{ overflow: 'auto' }}>
      <div className="panel-header">
        <span>Trade Builder</span>
        <div className="panel-tabs">
          <button
            className={`panel-tab ${strategy === 'butterfly' ? 'active' : ''}`}
            onClick={() => setStrategy('butterfly')}
          >
            Butterfly
          </button>
          <button
            className={`panel-tab ${strategy === 'vertical' ? 'active' : ''}`}
            onClick={() => setStrategy('vertical')}
          >
            Vertical
          </button>
        </div>
      </div>

      <div style={{ padding: '8px 12px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={optionType} onChange={e => setOptionType(e.target.value as 'CALL' | 'PUT')}>
          <option value="CALL">Call</option>
          <option value="PUT">Put</option>
        </select>

        {strategy === 'butterfly' ? (
          <>
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
              Center:
              <input
                type="number"
                value={centerStrike}
                onChange={e => setCenterStrike(e.target.value)}
                placeholder={String(Math.round(chain?.underlying_price || 5850))}
                style={{ width: '80px', marginLeft: '4px' }}
              />
            </label>
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
              Width:
              <input
                type="number"
                value={width}
                onChange={e => setWidth(e.target.value)}
                style={{ width: '50px', marginLeft: '4px' }}
              />
            </label>
          </>
        ) : (
          <>
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
              Long:
              <input
                type="number"
                value={longStrike}
                onChange={e => setLongStrike(e.target.value)}
                style={{ width: '80px', marginLeft: '4px' }}
              />
            </label>
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
              Short:
              <input
                type="number"
                value={shortStrike}
                onChange={e => setShortStrike(e.target.value)}
                style={{ width: '80px', marginLeft: '4px' }}
              />
            </label>
          </>
        )}

        <button className="primary" onClick={buildAndEvaluate} disabled={loading}>
          {loading ? '...' : 'Evaluate'}
        </button>
      </div>

      {evaluation && (
        <div>
          {/* Summary */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '8px', padding: '8px 12px', borderTop: '1px solid var(--border)',
          }}>
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>Max Profit</div>
              <div className="positive">${evaluation.max_profit.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>Max Loss</div>
              <div className="negative">${evaluation.max_loss.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>R:R Ratio</div>
              <div>{evaluation.risk_reward_ratio.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>Status</div>
              <div className={evaluation.passes_criteria ? 'positive' : 'negative'}>
                {evaluation.passes_criteria ? 'PASS' : 'FAIL'}
              </div>
            </div>
          </div>

          {evaluation.rejection_reasons.length > 0 && (
            <div style={{ padding: '4px 12px' }}>
              {evaluation.rejection_reasons.map((r, i) => (
                <div key={i} className="alert-bar" style={{ marginBottom: '2px' }}>[ALERT] {r}</div>
              ))}
            </div>
          )}

          {/* Risk Graph */}
          <div style={{ height: '180px', padding: '8px 0' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={evaluation.risk_graph}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00c853" stopOpacity={0.3} />
                    <stop offset="50%" stopColor="#00c853" stopOpacity={0} />
                    <stop offset="50%" stopColor="#ff1744" stopOpacity={0} />
                    <stop offset="95%" stopColor="#ff1744" stopOpacity={0.3} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="price"
                  tick={{ fill: '#555', fontSize: 10 }}
                  tickFormatter={v => v.toFixed(0)}
                />
                <YAxis
                  tick={{ fill: '#555', fontSize: 10 }}
                  tickFormatter={v => `$${v}`}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1a1a25', border: '1px solid #2a2a3a',
                    fontSize: '11px', fontFamily: 'monospace',
                  }}
                  formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
                  labelFormatter={v => `SPX: ${Number(v).toFixed(2)}`}
                />
                <ReferenceLine y={0} stroke="#2a2a3a" />
                <Area
                  type="monotone"
                  dataKey="pnl"
                  stroke="#2196f3"
                  fill="url(#pnlGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Legs */}
          <table>
            <thead>
              <tr>
                <th className="text-left">Action</th>
                <th>Strike</th>
                <th>Type</th>
                <th>Qty</th>
              </tr>
            </thead>
            <tbody>
              {evaluation.setup.legs.map((leg, i) => (
                <tr key={i}>
                  <td className={`text-left ${leg.action === 'BUY' ? 'positive' : 'negative'}`}>
                    {leg.action}
                  </td>
                  <td>{leg.strike}</td>
                  <td>{leg.option_type}</td>
                  <td>{leg.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
