import React from 'react';
import { useAppStore } from '../store/useAppStore';
import { Cpu, HardDrive, Thermometer, Music, Zap, Wifi } from 'lucide-react';
import { EmotionPet } from '../components/EmotionPet';
import { MicStreamPlayer } from '../components/MicStreamPlayer';
import { PCMicTester } from '../components/PCMicTester';
import { ChatPanel } from '../components/ChatPanel';

const CircularProgress = ({ value, label, icon: Icon, colorClass }: { value: number, label: string, icon: any, colorClass: string }) => {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center p-4 bg-cyber-navy/40 border border-cyber-navy rounded-xl">
      <div className="relative flex items-center justify-center w-32 h-32">
        <svg className="w-full h-full transform -rotate-90">
          {/* Background circle */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke="currentColor"
            strokeWidth="8"
            fill="transparent"
            className="text-cyber-dark"
          />
          {/* Progress circle */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke="currentColor"
            strokeWidth="8"
            fill="transparent"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className={`transition-all duration-500 ease-out ${colorClass}`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute flex flex-col items-center justify-center">
          <Icon className={`w-6 h-6 mb-1 ${colorClass}`} />
          <span className="text-xl font-bold">{value}%</span>
        </div>
      </div>
      <span className="mt-2 text-sm text-gray-400 font-medium uppercase tracking-wider">{label}</span>
    </div>
  );
};

const DashboardPage: React.FC = () => {
  const metrics = useAppStore(state => state.metrics);
  const emotion = useAppStore(state => state.emotion);
  const isConnected = useAppStore(state => state.isConnected);
  const deviceStatus = useAppStore(state => state.deviceStatus);

  return (
    <div className="flex-1 p-8 max-w-6xl mx-auto w-full space-y-8 animate-fade-in">
      
      {/* Header Info */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">Live Dashboard</h2>
          <p className="text-gray-400">Monitoring System Telemetry in Real-Time</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button 
            onClick={() => {
              const r = parseInt(localStorage.getItem('petRotation') || '0');
              const nextR = (r + 1) % 4;
              localStorage.setItem('petRotation', nextR.toString());
              useAppStore.getState().sendMessage({ action: "set_rotation", rotation: nextR });
            }}
            className="flex items-center gap-2 bg-cyber-navy/50 hover:bg-cyber-cyan/20 px-4 py-2 rounded-full border border-cyber-navy transition-colors cursor-pointer"
          >
            <span className="text-sm font-medium">Rotate Screen</span>
          </button>

          <div className="flex items-center gap-2 bg-cyber-navy/50 px-4 py-2 rounded-full border border-cyber-navy">
            <Music className="w-4 h-4 text-cyber-cyan" />
            <span className="text-sm font-medium truncate max-w-[150px]">
              {metrics.spotify}
            </span>
          </div>

          <div className="flex items-center gap-2 bg-cyber-navy/50 px-4 py-2 rounded-full border border-cyber-navy">
            <Wifi className={`w-4 h-4 ${deviceStatus.connected ? 'text-cyber-emerald animate-pulse' : 'text-gray-500'}`} />
            <span className="text-sm font-medium">
              M5Stack: {deviceStatus.connected ? `${deviceStatus.ip} (${deviceStatus.ssid})` : 'Offline'}
            </span>
          </div>

          <div className="flex items-center gap-2 bg-cyber-navy/50 px-4 py-2 rounded-full border border-cyber-navy">
            <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-cyber-emerald animate-ping' : 'bg-red-500'}`}></div>
            <span className="text-sm font-medium">Web WS {isConnected ? 'Active' : 'Offline'}</span>
          </div>

          <PCMicTester />
          <MicStreamPlayer />
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        
        {/* Metrics Row */}
        <div className="col-span-1 md:col-span-3 grid grid-cols-2 md:grid-cols-4 gap-6">
          <CircularProgress 
            value={metrics.cpu} 
            label="CPU Usage" 
            icon={Cpu} 
            colorClass="text-cyber-cyan" 
          />
          <CircularProgress 
            value={metrics.ram} 
            label="RAM Usage" 
            icon={HardDrive} 
            colorClass="text-purple-400" 
          />
          <CircularProgress 
            value={metrics.gpu} 
            label="GPU Usage" 
            icon={Zap} 
            colorClass="text-yellow-400" 
          />
          <div className="flex flex-col items-center justify-center p-4 bg-cyber-navy/40 border border-cyber-navy rounded-xl">
            <Thermometer className={`w-12 h-12 mb-2 ${metrics.temp > 80 ? 'text-red-500 animate-bounce' : 'text-cyber-emerald'}`} />
            <span className="text-3xl font-bold">{metrics.temp}°C</span>
            <span className="mt-2 text-sm text-gray-400 font-medium uppercase tracking-wider">CPU Temp</span>
          </div>
        </div>

        {/* Pet Status Panel — rich animated EmotionPet */}
        <div className="col-span-1 bg-cyber-navy/40 border border-cyber-navy rounded-xl p-6 flex flex-col items-center justify-center relative overflow-visible">
          <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-cyber-cyan/5 to-transparent pointer-events-none" />
          
          <h3 className="text-sm text-gray-400 uppercase tracking-widest mb-4 relative z-10">Pet Status</h3>
          
          <div className="relative z-10">
            <EmotionPet emotion={emotion} size="md" />
          </div>
        </div>

      </div>

      {/* Chat Transcript Row */}
      <div className="h-80 animate-fade-in">
        <ChatPanel />
      </div>

    </div>
  );
};

export default DashboardPage;
