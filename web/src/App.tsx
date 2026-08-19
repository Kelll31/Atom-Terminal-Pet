import { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import { useAppStore } from './store/useAppStore';
import InstallPage from './pages/InstallPage';
import DashboardPage from './pages/DashboardPage';
import RulesPage from './pages/RulesPage';
import DebugPage from './pages/DebugPage';
import SettingsPage from './pages/SettingsPage';

function App() {
  const isConnected = useAppStore(state => state.isConnected);
  const connectWebSocket = useAppStore(state => state.connectWebSocket);

  useEffect(() => {
    connectWebSocket();
  }, [connectWebSocket]);

  return (
    <Router>
      <div className="min-h-screen bg-cyber-dark text-white font-sans flex flex-col">
        {/* Simple Header */}
        <header className="border-b border-cyber-navy p-4 flex justify-between items-center bg-cyber-dark/80 backdrop-blur-md sticky top-0 z-50">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded bg-cyber-navy border border-cyber-cyan flex items-center justify-center">
                <span className="text-cyber-cyan font-bold text-xl leading-none">A</span>
              </div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-cyber-cyan to-cyber-emerald bg-clip-text text-transparent">
                Atom-Terminal-Pet
              </h1>
            </div>
            <nav className="flex gap-4 ml-4">
              <Link to="/install" className="text-gray-400 hover:text-cyber-cyan transition-colors">Flasher</Link>
              <Link to="/dashboard" className="text-gray-400 hover:text-cyber-cyan transition-colors">Dashboard</Link>
              <Link to="/rules" className="text-gray-400 hover:text-cyber-cyan transition-colors">Rules</Link>
              <Link to="/settings" className="text-gray-400 hover:text-cyber-cyan transition-colors">AI Settings</Link>
              <Link to="/debug" className="text-gray-400 hover:text-cyber-cyan transition-colors">Debug</Link>
            </nav>
          </div>
          <div className="flex gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-cyber-emerald shadow-[0_0_8px_#00ff9d]' : 'bg-red-500'}`}></div>
              {isConnected ? 'Backend Connected' : 'Backend Disconnected'}
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 flex flex-col">
          <Routes>
            <Route path="/" element={<Navigate to="/install" replace />} />
            <Route path="/install" element={<InstallPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/debug" element={<DebugPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
