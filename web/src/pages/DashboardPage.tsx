import React from 'react';
import { Cpu, HardDrive, Music, RotateCw, Thermometer, Usb, Wifi, Zap } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { PatrickPet } from '../components/PatrickPet';
import { MicStreamPlayer } from '../components/MicStreamPlayer';
import { PCMicTester } from '../components/PCMicTester';
import { ChatPanel } from '../components/ChatPanel';
import { TaskTimeline } from '../components/TaskTimeline';

const MetricTile: React.FC<{
  label: string;
  value: number;
  unit?: string;
  icon: React.ElementType;
  accent: string;
  danger?: boolean;
}> = ({ label, value, unit = '%', icon: Icon, accent, danger }) => (
  <div className="card p-4">
    <div className="mb-3 flex items-center justify-between">
      <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</span>
      <Icon className={`h-4 w-4 ${danger ? 'text-red-400' : accent}`} />
    </div>
    <div className="flex items-end gap-1">
      <span className={`text-3xl font-bold tabular-nums ${danger ? 'text-red-300' : 'text-white'}`}>
        {value}
      </span>
      <span className="pb-1 text-sm text-slate-500">{unit}</span>
    </div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/5">
      <div
        className={`h-full rounded-full transition-[width] duration-700 ease-out ${
          danger ? 'bg-red-400' : 'bg-cyber-cyan'
        }`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  </div>
);

const DashboardPage: React.FC = () => {
  const metrics = useAppStore(state => state.metrics);
  const emotion = useAppStore(state => state.emotion);
  const petSays = useAppStore(state => state.petSays);
  const isConnected = useAppStore(state => state.isConnected);
  const deviceStatus = useAppStore(state => state.deviceStatus);
  const tasks = useAppStore(state => state.tasks);
  const sendMessage = useAppStore(state => state.sendMessage);

  const rotateScreen = () => {
    const next = (Number(localStorage.getItem('petRotation') ?? '0') + 1) % 4;
    localStorage.setItem('petRotation', String(next));
    sendMessage({ action: 'set_rotation', rotation: next });
  };

  const pat = () => sendMessage({ action: 'speak', emotion: 'love', text: 'Погладили!' });

  return (
    <div className="animate-fade-in mx-auto w-full max-w-7xl space-y-6 p-4 md:p-6">
      {/* Статусная строка */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`chip ${deviceStatus.connected ? 'border-emerald-400/30 text-emerald-200' : 'text-slate-400'}`}>
          {deviceStatus.transport === 'usb' ? <Usb className="h-3.5 w-3.5" /> : <Wifi className="h-3.5 w-3.5" />}
          {deviceStatus.connected
            ? `Питомец на связи · ${deviceStatus.transport === 'usb' ? 'USB' : deviceStatus.ip}`
            : 'Питомец не подключён'}
        </span>

        <span className={`chip ${isConnected ? 'border-cyan-400/30 text-cyan-200' : 'border-red-400/30 text-red-300'}`}>
          <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
          {isConnected ? 'Сервер онлайн' : 'Сервер недоступен'}
        </span>

        {metrics.spotify && (
          <span className="chip max-w-xs text-slate-300">
            <Music className="h-3.5 w-3.5 text-cyber-cyan" />
            <span className="truncate">{metrics.spotify}</span>
          </span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <PCMicTester />
          <MicStreamPlayer />
          <button onClick={rotateScreen} className="chip text-slate-300 hover:text-white" title="Повернуть экран питомца">
            <RotateCw className="h-3.5 w-3.5" /> Экран
          </button>
        </div>
      </div>

      {/* Метрики */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile label="Процессор" value={metrics.cpu} icon={Cpu} accent="text-cyber-cyan" danger={metrics.cpu > 90} />
        <MetricTile label="Память" value={metrics.ram} icon={HardDrive} accent="text-violet-300" danger={metrics.ram > 92} />
        <MetricTile label="Видеокарта" value={metrics.gpu} icon={Zap} accent="text-amber-300" />
        <MetricTile label="Температура" value={metrics.temp} unit="°C" icon={Thermometer} accent="text-emerald-300" danger={metrics.temp > 82} />
      </div>

      {/* Питомец + диалог */}
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="card flex flex-col items-center justify-center gap-2 p-6 lg:col-span-4">
          <PatrickPet emotion={emotion} size="lg" onPat={pat} caption={petSays || undefined} />
        </div>

        <div className="h-[26rem] lg:col-span-8 lg:h-[30rem]">
          <ChatPanel />
        </div>
      </div>

      {/* Что делает агент */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400">Что делает Атом</h2>
        <TaskTimeline
          tasks={tasks.slice(0, 8)}
          emptyHint="Поставьте задачу в диалоге — здесь появятся шаги её выполнения."
        />
      </section>
    </div>
  );
};

export default DashboardPage;
