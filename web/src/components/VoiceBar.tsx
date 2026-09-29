import React, { useEffect, useState } from 'react';
import { Ear, Hand, MessageCircle, Mic, MicOff, Radio, Square } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { API_BASE } from '../config';

/**
 * Живая полоска голосового режима: видно, слышит ли питомец,
 * открыт ли диалог без обращения по имени, и можно ли его перебить.
 */
export const VoiceBar: React.FC = () => {
  const voice = useAppStore(state => state.voice);
  const agentStatus = useAppStore(state => state.agentStatus);
  const interruptPet = useAppStore(state => state.interruptPet);

  const [config, setConfig] = useState<{ enabled: boolean; live_mode: boolean; engine: string } | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch(`${API_BASE}/api/voice`)
        .then(res => res.json())
        .then(data => alive && setConfig(data))
        .catch(() => undefined);
    };
    load();
    const timer = setInterval(load, 10000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const petSpeaking = voice.petSpeaking || agentStatus.state === 'speaking';
  const bars = 12;
  const active = Math.round(Math.min(1, voice.level * 6) * bars);

  return (
    <div className="card flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="flex items-center gap-2">
        {config?.enabled === false ? (
          <MicOff className="h-4 w-4 text-slate-500" />
        ) : voice.speaking ? (
          <Mic className="h-4 w-4 text-emerald-300" />
        ) : (
          <Ear className="h-4 w-4 text-cyber-cyan" />
        )}
        <span className="text-sm text-slate-300">
          {config?.enabled === false
            ? 'Голос выключен'
            : voice.speaking
              ? 'Слышу вас'
              : petSpeaking
                ? 'Говорю'
                : 'Слушаю'}
        </span>
      </div>

      {/* Индикатор громкости */}
      <div className="flex h-5 items-end gap-[3px]">
        {Array.from({ length: bars }, (_, i) => (
          <span
            key={i}
            className={`w-[3px] rounded-sm transition-all duration-100 ${
              i < active ? (i > bars - 4 ? 'bg-amber-300' : 'bg-cyber-cyan') : 'bg-white/10'
            }`}
            style={{ height: `${6 + i * 1.2}px` }}
          />
        ))}
      </div>

      {voice.conversationOpen ? (
        <span className="chip border-emerald-400/30 text-emerald-200">
          <MessageCircle className="h-3.5 w-3.5" />
          Живой диалог · {Math.round(voice.conversationLeft)}с
        </span>
      ) : (
        <span className="chip text-slate-400">
          <Radio className="h-3.5 w-3.5" />
          Скажите «Патрик, …»
        </span>
      )}

      {config?.engine === 'whisper' && (
        <span className="chip text-violet-200">whisper</span>
      )}

      <button
        onClick={interruptPet}
        disabled={!petSpeaking}
        className={`chip ml-auto ${
          petSpeaking ? 'border-red-400/40 text-red-200 hover:bg-red-500/10' : 'text-slate-500'
        }`}
        title="Прервать питомца (то же делает кнопка на устройстве или встряска)"
      >
        <Square className="h-3.5 w-3.5" /> Перебить
      </button>

      {voice.lastIgnored && (
        <span className="flex items-center gap-1 text-xs text-slate-500" title="Услышал, но обращения по имени не было">
          <Hand className="h-3 w-3" /> мимо: «{voice.lastIgnored.slice(0, 40)}»
        </span>
      )}
    </div>
  );
};

export default VoiceBar;
