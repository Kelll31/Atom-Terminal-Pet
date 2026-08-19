import React, { useEffect, useState } from 'react';
import {
  AlertTriangle, Brain, CheckCircle2, FolderOpen, Play, Save, Shield, Trash2, Volume2,
} from 'lucide-react';
import { API_BASE } from '../config';

interface Settings {
  api_key: string;
  api_key_set: boolean;
  base_url: string;
  model_name: string;
  temperature: number;
  max_steps: number;
  pet_name: string;
  wake_words: string[];
  require_wake_word: boolean;
  speak_replies: boolean;
  audio_output: 'device' | 'pc' | 'both';
  autonomy: 'ask' | 'auto_safe' | 'full';
  allowed_roots: string[];
  mcp_enabled: boolean;
}

const AUDIO_OUTPUTS: { value: Settings['audio_output']; label: string; hint: string }[] = [
  { value: 'both', label: 'Питомец + ПК', hint: 'Слышно и из динамика M5, и из колонок компьютера' },
  { value: 'device', label: 'Только питомец', hint: 'Голос звучит из динамика Atomic Echo Base' },
  { value: 'pc', label: 'Только ПК', hint: 'Голос идёт в колонки компьютера — громче и чище' },
];

const PRESETS: Record<string, { base_url: string; model_name: string }> = {
  deepseek: { base_url: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  openrouter: { base_url: 'https://openrouter.ai/api/v1', model_name: 'anthropic/claude-sonnet-4.5' },
  openai: { base_url: '', model_name: 'gpt-4o-mini' },
  ollama: { base_url: 'http://localhost:11434/v1', model_name: 'qwen2.5:7b' },
};

const AUTONOMY_OPTIONS: { value: Settings['autonomy']; title: string; hint: string }[] = [
  { value: 'ask', title: 'Спрашивать всегда', hint: 'Любое действие с системой — только после вашего подтверждения.' },
  { value: 'auto_safe', title: 'Разумный баланс', hint: 'Чтение и безопасные действия — сам, опасные — с подтверждением.' },
  { value: 'full', title: 'Полное доверие', hint: 'Выполняет всё без вопросов. Только если вы понимаете риск.' },
];

const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [newRoot, setNewRoot] = useState('');
  const [status, setStatus] = useState<{ type: 'idle' | 'loading' | 'ok' | 'error'; message: string }>({
    type: 'idle',
    message: '',
  });

  useEffect(() => {
    fetch(`${API_BASE}/api/settings`)
      .then(res => res.json())
      .then(setSettings)
      .catch(() => setStatus({ type: 'error', message: 'Сервер Атома недоступен.' }));
  }, []);

  const patch = (changes: Partial<Settings>) =>
    setSettings(current => (current ? { ...current, ...changes } : current));

  const save = async (extra: Partial<Settings> = {}) => {
    if (!settings) return;
    setStatus({ type: 'loading', message: 'Сохраняю…' });
    const payload: Record<string, unknown> = {
      base_url: settings.base_url,
      model_name: settings.model_name,
      temperature: settings.temperature,
      max_steps: settings.max_steps,
      pet_name: settings.pet_name,
      wake_words: settings.wake_words,
      require_wake_word: settings.require_wake_word,
      speak_replies: settings.speak_replies,
      audio_output: settings.audio_output,
      autonomy: settings.autonomy,
      allowed_roots: settings.allowed_roots,
      mcp_enabled: settings.mcp_enabled,
      ...extra,
    };
    if (apiKey.trim()) payload.api_key = apiKey.trim();

    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setSettings(data);
      setApiKey('');
      setStatus({ type: 'ok', message: 'Настройки сохранены.' });
    } catch (error) {
      setStatus({ type: 'error', message: `Не удалось сохранить: ${error}` });
    }
  };

  const testConnection = async () => {
    if (!settings) return;
    setStatus({ type: 'loading', message: 'Проверяю связь с моделью…' });
    try {
      const res = await fetch(`${API_BASE}/api/settings/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKey.trim(),
          base_url: settings.base_url,
          model_name: settings.model_name,
        }),
      });
      const data = await res.json();
      setStatus(
        data.status === 'success'
          ? { type: 'ok', message: `Модель ответила: «${data.message}»` }
          : { type: 'error', message: data.message },
      );
    } catch (error) {
      setStatus({ type: 'error', message: `Сеть недоступна: ${error}` });
    }
  };

  if (!settings) {
    return <div className="p-8 text-sm text-slate-400">Загружаю настройки…</div>;
  }

  return (
    <div className="animate-fade-in mx-auto w-full max-w-4xl space-y-6 p-4 md:p-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Настройки</h1>
        <p className="mt-1 text-sm text-slate-400">Мозг, характер и права доступа вашего питомца.</p>
      </header>

      {/* Модель */}
      <section className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-cyber-cyan" />
          <h2 className="font-semibold text-white">Модель</h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {Object.entries(PRESETS).map(([name, preset]) => (
            <button
              key={name}
              onClick={() => patch(preset)}
              className={`chip ${settings.base_url === preset.base_url ? 'border-cyber-cyan/60 text-cyan-200' : 'text-slate-300'}`}
            >
              {name}
            </button>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">Base URL</span>
            <input
              className="field"
              value={settings.base_url}
              placeholder="Пусто — официальный OpenAI"
              onChange={e => patch({ base_url: e.target.value })}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">Модель</span>
            <input
              className="field"
              value={settings.model_name}
              onChange={e => patch({ model_name: e.target.value })}
            />
          </label>

          <label className="space-y-1.5 md:col-span-2">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              API-ключ {settings.api_key_set && <span className="text-emerald-300">— сохранён ({settings.api_key})</span>}
            </span>
            <input
              className="field"
              type="password"
              value={apiKey}
              placeholder={settings.api_key_set ? 'Оставьте пустым, чтобы не менять' : 'sk-…'}
              onChange={e => setApiKey(e.target.value)}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Температура: {settings.temperature.toFixed(1)}
            </span>
            <input
              type="range"
              min={0}
              max={1.2}
              step={0.1}
              value={settings.temperature}
              onChange={e => patch({ temperature: Number(e.target.value) })}
              className="w-full accent-cyan-400"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Максимум шагов на задачу: {settings.max_steps}
            </span>
            <input
              type="range"
              min={3}
              max={30}
              step={1}
              value={settings.max_steps}
              onChange={e => patch({ max_steps: Number(e.target.value) })}
              className="w-full accent-cyan-400"
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-3">
          <button onClick={() => save()} className="btn-primary">
            <Save className="h-4 w-4" /> Сохранить
          </button>
          <button onClick={testConnection} className="btn-ghost">
            <Play className="h-4 w-4 text-cyber-cyan" /> Проверить связь
          </button>
        </div>
      </section>

      {/* Характер */}
      <section className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Volume2 className="h-5 w-5 text-cyber-cyan" />
          <h2 className="font-semibold text-white">Питомец</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">Кличка</span>
            <input
              className="field"
              value={settings.pet_name}
              onChange={e => patch({ pet_name: e.target.value })}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Слова-обращения (через запятую)
            </span>
            <input
              className="field"
              value={settings.wake_words.join(', ')}
              onChange={e =>
                patch({ wake_words: e.target.value.split(',').map(w => w.trim().toLowerCase()).filter(Boolean) })
              }
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => patch({ require_wake_word: !settings.require_wake_word })}
            className={`chip ${settings.require_wake_word ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
          >
            {settings.require_wake_word ? 'Отзывается только на кличку' : 'Реагирует на любую речь'}
          </button>
          <button
            onClick={() => patch({ speak_replies: !settings.speak_replies })}
            className={`chip ${settings.speak_replies ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
          >
            {settings.speak_replies ? 'Озвучивает ответы' : 'Молчит (только текст)'}
          </button>
          <button
            onClick={() => patch({ mcp_enabled: !settings.mcp_enabled })}
            className={`chip ${settings.mcp_enabled ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
          >
            MCP-серверы: {settings.mcp_enabled ? 'включены' : 'выключены'}
          </button>
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-slate-400">Куда выводить голос</div>
          <div className="grid gap-3 md:grid-cols-3">
            {AUDIO_OUTPUTS.map(option => (
              <button
                key={option.value}
                onClick={() => save({ audio_output: option.value })}
                className={`rounded-xl border p-3 text-left transition-colors ${
                  settings.audio_output === option.value
                    ? 'border-cyber-cyan/60 bg-cyber-cyan/10'
                    : 'border-white/10 bg-white/5 hover:border-white/20'
                }`}
              >
                <div className="text-sm font-semibold text-white">{option.label}</div>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">{option.hint}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button onClick={() => save()} className="btn-primary w-fit">
            <Save className="h-4 w-4" /> Сохранить
          </button>
          <button
            onClick={async () => {
              setStatus({ type: 'loading', message: 'Проверяю звук…' });
              try {
                const res = await fetch(`${API_BASE}/api/say`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ text: 'Проверка связи. Меня слышно?', emotion: 'happy' }),
                });
                const data = await res.json();
                setStatus({ type: 'ok', message: `Отправлено ${data.bytes_sent} байт → ${data.route}` });
              } catch (error) {
                setStatus({ type: 'error', message: `Не получилось: ${error}` });
              }
            }}
            className="btn-ghost"
          >
            <Volume2 className="h-4 w-4 text-cyber-cyan" /> Проверить звук
          </button>
        </div>
      </section>

      {/* Автономия */}
      <section className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-amber-300" />
          <h2 className="font-semibold text-white">Права и безопасность</h2>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          {AUTONOMY_OPTIONS.map(option => (
            <button
              key={option.value}
              onClick={() => save({ autonomy: option.value })}
              className={`rounded-xl border p-4 text-left transition-colors ${
                settings.autonomy === option.value
                  ? 'border-cyber-cyan/60 bg-cyber-cyan/10'
                  : 'border-white/10 bg-white/5 hover:border-white/20'
              }`}
            >
              <div className="text-sm font-semibold text-white">{option.title}</div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">{option.hint}</p>
            </button>
          ))}
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400">
            <FolderOpen className="h-4 w-4" /> Каталоги, доступные питомцу
          </div>
          {settings.allowed_roots.length === 0 && (
            <p className="text-xs text-amber-300">
              Пока не добавлено ни одного каталога — файловые инструменты работать не будут.
            </p>
          )}
          <div className="space-y-2">
            {settings.allowed_roots.map(root => (
              <div key={root} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/30 px-3 py-2">
                <span className="flex-1 truncate font-mono text-xs text-slate-300">{root}</span>
                <button
                  onClick={() => save({ allowed_roots: settings.allowed_roots.filter(r => r !== root) })}
                  className="text-slate-500 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className="field flex-1"
              placeholder="D:/projects/my-app"
              value={newRoot}
              onChange={e => setNewRoot(e.target.value)}
            />
            <button
              onClick={() => {
                const value = newRoot.trim().replace(/\\/g, '/');
                if (!value) return;
                save({ allowed_roots: [...settings.allowed_roots, value] });
                setNewRoot('');
              }}
              className="btn-ghost"
            >
              Добавить
            </button>
          </div>
        </div>
      </section>

      {status.type !== 'idle' && (
        <div
          className={`card flex items-start gap-3 p-4 text-sm ${
            status.type === 'error'
              ? 'border-red-400/30 text-red-200'
              : status.type === 'ok'
                ? 'border-emerald-400/30 text-emerald-200'
                : 'text-slate-300'
          }`}
        >
          {status.type === 'error' ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          ) : status.type === 'ok' ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <div className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-cyber-cyan border-t-transparent" />
          )}
          <span className="break-all">{status.message}</span>
        </div>
      )}
    </div>
  );
};

export default SettingsPage;
