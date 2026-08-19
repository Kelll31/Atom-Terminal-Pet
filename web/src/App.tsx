import { useEffect } from 'react';
import { BrowserRouter as Router, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Bug, LayoutDashboard, Settings2, SlidersHorizontal, Usb, Wrench } from 'lucide-react';
import { useAppStore } from './store/useAppStore';
import { PatrickPet } from './components/PatrickPet';
import ApprovalDock from './components/ApprovalDock';
import InstallPage from './pages/InstallPage';
import DashboardPage from './pages/DashboardPage';
import RulesPage from './pages/RulesPage';
import DebugPage from './pages/DebugPage';
import SettingsPage from './pages/SettingsPage';
import ToolsPage from './pages/ToolsPage';

const NAV = [
  { to: '/dashboard', label: 'Панель', icon: LayoutDashboard },
  { to: '/tools', label: 'Инструменты', icon: Wrench },
  { to: '/rules', label: 'Правила', icon: SlidersHorizontal },
  { to: '/settings', label: 'Настройки', icon: Settings2 },
  { to: '/install', label: 'Прошивка', icon: Usb },
  { to: '/debug', label: 'Отладка', icon: Bug },
];

function Navigation() {
  const location = useLocation();
  return (
    <nav className="flex gap-1 overflow-x-auto">
      {NAV.map(({ to, label, icon: Icon }) => {
        const active = location.pathname === to;
        return (
          <Link
            key={to}
            to={to}
            className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
              active ? 'bg-cyber-cyan/15 text-cyan-200' : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <Icon className="h-4 w-4" />
            <span className="hidden sm:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function App() {
  const isConnected = useAppStore(state => state.isConnected);
  const emotion = useAppStore(state => state.emotion);
  const connectWebSocket = useAppStore(state => state.connectWebSocket);
  const agentStatus = useAppStore(state => state.agentStatus);

  useEffect(() => {
    connectWebSocket();
  }, [connectWebSocket]);

  return (
    <Router>
      <div className="flex min-h-screen flex-col bg-cyber-dark">
        <header className="sticky top-0 z-40 border-b border-white/5 bg-cyber-dark/85 backdrop-blur-md">
          <div className="mx-auto flex w-full max-w-7xl items-center gap-4 px-4 py-2.5">
            <Link to="/dashboard" className="flex shrink-0 items-center gap-2">
              <PatrickPet emotion={emotion} size="sm" showLabel={false} />
              <div className="hidden leading-tight md:block">
                <div className="text-sm font-bold text-white">Атом</div>
                <div className="text-[11px] text-slate-500">питомец-помощник</div>
              </div>
            </Link>

            <Navigation />

            <div className="ml-auto flex items-center gap-2">
              {agentStatus.state !== 'idle' && (
                <span className="chip hidden border-cyan-400/30 text-cyan-200 sm:inline-flex">
                  {agentStatus.state === 'working'
                    ? `работает: ${agentStatus.tool ?? ''}`
                    : agentStatus.state === 'thinking'
                      ? 'думает'
                      : 'говорит'}
                </span>
              )}
              <span className={`chip ${isConnected ? 'text-emerald-200' : 'border-red-400/30 text-red-300'}`}>
                <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span className="hidden sm:inline">{isConnected ? 'онлайн' : 'нет связи'}</span>
              </span>
            </div>
          </div>
        </header>

        <main className="flex flex-1 flex-col">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/install" element={<InstallPage />} />
            <Route path="/debug" element={<DebugPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>

        <ApprovalDock />
      </div>
    </Router>
  );
}

export default App;
