import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { api } from '../api/client';
import type { RiskStatus, Scenario, Alert } from '../types';

const S: Record<string, React.CSSProperties> = {
  wrap: { padding: 12 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 12 },
  card: { background: '#111118', border: '1px solid #1e1e2e', borderRadius: 6, padding: '8px 12px' },
  label: { fontSize: 9, color: '#666', textTransform: 'uppercase' as const, letterSpacing: 1 },
  val: { fontSize: 16, fontWeight: 700, marginTop: 2 },
  bar: { height: 4, background: '#1e1e2e', borderRadius: 2, marginTop: 4 },
  barFill: { height: '100%', borderRadius: 2, transition: 'width 0.3s' },
  alertList: { maxHeight: 200, overflow: 'auto', marginBottom: 12 },
  alert: { padding: '6px 10px', marginBottom: 4, borderRadius: 4, fontSize: 11, display: 'flex', justifyContent: 'space-between' },
  alertBreach: { background: 'rgba(255, 23, 68, 0.1)', border: '1px solid rgba(255, 23, 68, 0.3)' },
  alertWarn: { background: 'rgba(255, 152, 0, 0.1)', border: '1px solid rgba(255, 152, 0, 0.3)' },
  sectionTitle: { fontSize: 11, color: '#888', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 1 },
};

function barColor(pct: number): string {
  if (pct >= 100) return '#ff1744';
  if (pct >= 80) return '#ff9800';
  return '#00e676';
}

export function RiskPanel() {
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);

  useEffect(() => {
    const load = () => {
      api.risk.status().then((d) => setRisk(d as RiskStatus));
      api.risk.scenarios().then((d) => setScenarios(d as Scenario[]));
    };
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, []);

  if (!risk) return <div style={S.wrap}>Loading risk...</div>;

  const checks = risk.checks;

  return (
    <div style={S.wrap}>
      <div style={{ ...S.sectionTitle, color: risk.status === 'BREACH' ? '#ff1744' : '#00e676', fontWeight: 700, fontSize: 13, marginBottom: 10 }}>
        Risk Status: {risk.status}
      </div>

      <div style={S.grid}>
        {Object.entries(checks).map(([key, check]) => {
          if (!check.pct_used && check.pct_used !== 0) return null;
          const pct = Math.min(check.pct_used, 100);
          return (
            <div key={key} style={{ ...S.card, borderColor: check.breached ? '#ff1744' : '#1e1e2e' }}>
              <div style={S.label}>{key.replace(/_/g, ' ')}</div>
              <div style={S.val}>
                {typeof check.value === 'number' ? check.value.toFixed(1) : check.value}
                <span style={{ fontSize: 10, color: '#555', marginLeft: 4 }}>/ {check.limit}</span>
              </div>
              <div style={S.bar}>
                <div style={{ ...S.barFill, width: `${pct}%`, background: barColor(pct) }} />
              </div>
            </div>
          );
        })}
      </div>

      {risk.alerts.length > 0 && (
        <>
          <div style={S.sectionTitle}>Active Alerts</div>
          <div style={S.alertList}>
            {risk.alerts.map((alert: Alert, i: number) => (
              <div key={i} style={{ ...S.alert, ...(alert.level === 'BREACH' ? S.alertBreach : S.alertWarn) }}>
                <span>[{alert.level}] {alert.message}</span>
                <span style={{ color: '#555' }}>{new Date(alert.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={S.sectionTitle}>Max Loss Scenarios (SPX Move)</div>
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={scenarios}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
            <XAxis dataKey="move_pct" stroke="#555" tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${v}%`} />
            <YAxis stroke="#555" tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v}`} />
            <Tooltip
              contentStyle={{ background: '#111118', border: '1px solid #333', fontSize: 11 }}
              formatter={(v: number) => [`$${v.toFixed(2)}`, 'Est. P&L']}
            />
            <ReferenceLine y={0} stroke="#444" />
            <Bar dataKey="estimated_pnl">
              {scenarios.map((entry, i) => (
                <Cell key={i} fill={entry.estimated_pnl >= 0 ? '#00e676' : '#ff1744'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
