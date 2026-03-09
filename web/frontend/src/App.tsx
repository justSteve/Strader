import { Layout } from './components/Layout';
import { MarketContextBar } from './components/MarketContextBar';
import { OptionsChainGrid } from './components/OptionsChain';
import { PositionDashboard } from './components/PositionDashboard';
import { TradeBuilder } from './components/TradeBuilder';
import { PnLChart } from './components/PnLChart';
import { RiskPanel } from './components/RiskPanel';

const tabs = [
  { id: 'chain', label: 'Options Chain', shortcut: '1', component: <OptionsChainGrid /> },
  { id: 'positions', label: 'Positions', shortcut: '2', component: <PositionDashboard /> },
  { id: 'trade', label: 'Trade Builder', shortcut: '3', component: <TradeBuilder /> },
  { id: 'pnl', label: 'P&L', shortcut: '4', component: <PnLChart /> },
  { id: 'risk', label: 'Risk', shortcut: '5', component: <RiskPanel /> },
];

export default function App() {
  return <Layout tabs={tabs} topBar={<MarketContextBar />} />;
}
