import { useState, useEffect, useCallback } from 'react'
import { MarketContextBar } from './components/MarketContextBar/MarketContextBar'
import { OptionsChain } from './components/OptionsChain/OptionsChain'
import { PositionDashboard } from './components/PositionDashboard/PositionDashboard'
import { TradeBuilder } from './components/TradeBuilder/TradeBuilder'
import { PnLChart } from './components/PnLChart/PnLChart'
import { RiskPanel } from './components/RiskPanel/RiskPanel'
import type { Tab } from './types'

const TABS: { id: Tab; label: string; key: string }[] = [
  { id: 'chain', label: 'Options Chain', key: '1' },
  { id: 'positions', label: 'Positions', key: '2' },
  { id: 'builder', label: 'Trade Builder', key: '3' },
  { id: 'pnl', label: 'P&L', key: '4' },
  { id: 'risk', label: 'Risk', key: '5' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chain')

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
    const tab = TABS.find(t => t.key === e.key)
    if (tab) setActiveTab(tab.id)
  }, [])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <>
      <MarketContextBar />
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab ${activeTab === t.id ? 'active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
            <span className="kbd">{t.key}</span>
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {activeTab === 'chain' && <OptionsChain />}
        {activeTab === 'positions' && <PositionDashboard />}
        {activeTab === 'builder' && <TradeBuilder />}
        {activeTab === 'pnl' && <PnLChart />}
        {activeTab === 'risk' && <RiskPanel />}
      </div>
    </>
  )
}
