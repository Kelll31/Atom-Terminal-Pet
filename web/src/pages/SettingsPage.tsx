import React, { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, AppWindow, Brain, CheckCircle2, Download, FolderOpen, Mic, Play, RefreshCw, Save,
  Search, Shield, Trash2, Volume2,
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

  voice_enabled: boolean;
  live_mode: boolean;
  conversation_window_sec: number;
  vad_sensitivity: number;
  vad_min_level: number;
  endpoint_silence_sec: number;
  barge_in: boolean;
  stt_engine: 'vosk' | 'whisper';
  stt_model: string;
  stt_base_url: string;
  stt_api_key: string;
  stt_api_key_set: boolean;

  auto_check_updates: boolean;
  update_url: string;
  panel_window: boolean;
}

interface UpdateInfo {
  version: string;
  url: string;
  size: number;
  notes: string;
  page: string;
}

interface UpdateState {
  current: string;
  available: UpdateInfo | null;
  last_check: number;
  last_error: string;
  downloading: boolean;
  progress: number;
  installable: boolean;
  from_sources: boolean;
}

const AUDIO_OUTPUTS: { value: Settings['audio_output']; label: string; hint: string }[] = [
  { value: 'both', label: 'Питомец + ПК', hint: 'Слышно и из динамика M5, и из колонок компьютера' },
  { value: 'device', label: 'Только питомец', hint: 'Голос звучит из динамика Atomic Echo Base' },
  { value: 'pc', label: 'Только ПК', hint: 'Голос идёт в колонки компьютера — громче и чище' },
];

interface ModelInfo {
  id: string;
  type: string;
  state: string;
  context: number | null;
}

interface LocalServer {
  name: string;
  base_url: string;
  models: ModelInfo[];
}

interface Preset {
  id: string;
  label: string;
  base_url: string;
  model_name: string;
  local?: boolean;
}

const PRESETS: Preset[] = [
  { id: 'lmstudio', label: 'LM Studio / Bionic', base_url: 'http://127.0.0.1:1234/v1', model_name: '', local: true },
  { id: 'ollama', label: 'Ollama', base_url: 'http://127.0.0.1:11434/v1', model_name: '', local: true },
  { id: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  { id: 'openrouter', label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', model_name: 'anthropic/claude-sonnet-4.5' },
  { id: 'openai', label: 'OpenAI', base_url: '', model_name: 'gpt-4o-mini' },
];

// Тот же список хостов, что и на сервере (backend/ai/llm.py): для них ключ не нужен
const LOCAL_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '::1', 'host.docker.internal'];

const isLocalUrl = (url: string): boolean => {
  if (!url.trim()) return false;
  const host = url.replace(/^\w+:\/\//, '').split('/')[0].split(':')[0];
  return LOCAL_HOSTS.includes(host.toLowerCase());
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
  const [sttKey, setSttKey] = useState('');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [update, setUpdate] = useState<UpdateState | null>(null);
  const progressTimer = useRef<number | null>(null);
  const [status, setStatus] = useState<{ type: 'idle' | 'loading' | 'ok' | 'error'; message: string }>({
    type: 'idle',
    message: '',
  });

  useEffect(() => {
    fetch(`${API_BASE}/api/settings`)
      .then(res => res.json())
      .then(setSettings)
      .catch(() => setStatus({ type: 'error', message: 'Сервер Патрика недоступен.' }));

    fetch(`${API_BASE}/api/update`)
      .then(res => res.json())
      .then(setUpdate)
      .catch(() => undefined);

    return () => stopProgressPolling();
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
      voice_enabled: settings.voice_enabled,
      live_mode: settings.live_mode,
      conversation_window_sec: settings.conversation_window_sec,
      vad_sensitivity: settings.vad_sensitivity,
      vad_min_level: settings.vad_min_level,
      endpoint_silence_sec: settings.endpoint_silence_sec,
      barge_in: settings.barge_in,
      stt_engine: settings.stt_engine,
      stt_model: settings.stt_model,
      stt_base_url: settings.stt_base_url,
      autonomy: settings.autonomy,
      allowed_roots: settings.allowed_roots,
      mcp_enabled: settings.mcp_enabled,
      auto_check_updates: settings.auto_check_updates,
      update_url: settings.update_url,
      panel_window: settings.panel_window,
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
      if (data.status !== 'success') {
        setStatus({ type: 'error', message: data.message });
        return;
      }
      setStatus({
        type: data.tools_supported === false ? 'error' : 'ok',
        message: `Модель ответила: «${data.message}»${data.note ? ` — ${data.note}` : ''}`,
      });
    } catch (error) {
      setStatus({ type: 'error', message: `Сеть недоступна: ${error}` });
    }
  };

  /** Спрашивает у сервера модели, которые он готов отдать. */
  const loadModels = async (baseUrl: string, silent = false): Promise<ModelInfo[]> => {
    if (!silent) setStatus({ type: 'loading', message: 'Запрашиваю список моделей…' });
    try {
      const res = await fetch(`${API_BASE}/api/llm/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey.trim(), base_url: baseUrl, model_name: '' }),
      });
      const data = await res.json();
      if (data.status !== 'success') {
        setModels([]);
        if (!silent) setStatus({ type: 'error', message: `Список моделей не получен: ${data.message}` });
        return [];
      }

      const list: ModelInfo[] = data.models ?? [];
      setModels(list);
      if (!silent) {
        setStatus(
          list.length
            ? { type: 'ok', message: `Доступно моделей: ${list.length}. Выберите нужную и сохраните.` }
            : {
                type: 'error',
                message: data.skipped_embeddings
                  ? 'На сервере есть только модель-эмбеддер. Скачайте в нём чат-модель (лучше с поддержкой tool calling).'
                  : 'Сервер не отдал ни одной модели.',
              },
        );
      }
      return list;
    } catch (error) {
      setModels([]);
      if (!silent) setStatus({ type: 'error', message: `Сервер моделей недоступен: ${error}` });
      return [];
    }
  };

  /** Обходит типовые порты и подставляет первый найденный локальный сервер. */
  const discoverLocal = async () => {
    setStatus({ type: 'loading', message: 'Ищу локальный сервер моделей…' });
    try {
      const res = await fetch(`${API_BASE}/api/llm/discover`);
      const data = await res.json();
      const servers: LocalServer[] = data.servers ?? [];
      if (!servers.length) {
        setStatus({
          type: 'error',
          message: 'Локальный сервер не найден. Запустите LM Studio / Bionic и включите в нём сервер (вкладка Developer).',
        });
        return;
      }

      const server = servers.find(s => s.models.length) ?? servers[0];
      const best = server.models.find(m => m.state === 'loaded') ?? server.models[0];
      patch({ base_url: server.base_url, ...(best ? { model_name: best.id } : {}) });
      setModels(server.models);
      setStatus({
        type: server.models.length ? 'ok' : 'error',
        message: server.models.length
          ? `Найден ${server.name} на ${server.base_url}. Модель: ${best.id}. Нажмите «Сохранить».`
          : `Найден ${server.name} на ${server.base_url}, но чат-моделей в нём нет — скачайте модель в самой программе.`,
      });
    } catch (error) {
      setStatus({ type: 'error', message: `Поиск не удался: ${error}` });
    }
  };

  const stopProgressPolling = () => {
    if (progressTimer.current !== null) {
      window.clearInterval(progressTimer.current);
      progressTimer.current = null;
    }
  };

  const checkUpdate = async () => {
    setStatus({ type: 'loading', message: 'Проверяю обновления…' });
    try {
      const res = await fetch(`${API_BASE}/api/update/check`, { method: 'POST' });
      const data: UpdateState = await res.json();
      setUpdate(data);
      if (data.last_error) {
        setStatus({ type: 'error', message: `Не удалось проверить: ${data.last_error}` });
      } else if (data.available) {
        setStatus({ type: 'ok', message: `Доступна версия ${data.available.version}.` });
      } else {
        setStatus({ type: 'ok', message: `У вас последняя версия (${data.current}).` });
      }
    } catch (error) {
      setStatus({ type: 'error', message: `Проверка не удалась: ${error}` });
    }
  };

  const installUpdate = async () => {
    if (!update?.available) return;
    setStatus({ type: 'loading', message: 'Скачиваю установщик…' });

    // Пока идёт загрузка, спрашиваем прогресс: ответ на сам запрос придёт
    // только в конце, а показать проценты хочется сразу.
    stopProgressPolling();
    progressTimer.current = window.setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/update`);
        setUpdate(await res.json());
      } catch {
        stopProgressPolling();   // сервер уже закрылся ради установки
      }
    }, 1000);

    try {
      const res = await fetch(`${API_BASE}/api/update/install`, { method: 'POST' });
      const data = await res.json();
      stopProgressPolling();
      setStatus(
        data.status === 'success'
          ? {
              type: 'ok',
              message: 'Установщик запущен: подтвердите запрос Windows. Патрик закроется и откроется уже обновлённым.',
            }
          : { type: 'error', message: data.message },
      );
    } catch (error) {
      stopProgressPolling();
      setStatus({ type: 'error', message: `Обновление не удалось: ${error}` });
    }
  };

  const applyPreset = async (preset: Preset) => {
    patch({ base_url: preset.base_url, model_name: preset.model_name });
    setModels([]);
    if (preset.local) {
      const list = await loadModels(preset.base_url);
      const best = list.find(m => m.state === 'loaded') ?? list[0];
      if (best) patch({ base_url: preset.base_url, model_name: best.id });
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

        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.map(preset => (
            <button
              key={preset.id}
              onClick={() => applyPreset(preset)}
              className={`chip ${settings.base_url === preset.base_url ? 'border-cyber-cyan/60 text-cyan-200' : 'text-slate-300'}`}
            >
              {preset.label}
            </button>
          ))}
          <button onClick={discoverLocal} className="chip border-emerald-400/40 text-emerald-200">
            <Search className="h-3.5 w-3.5" /> Найти локальную модель
          </button>
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
            {isLocalUrl(settings.base_url) && (
              <span className="block text-[11px] text-emerald-300">
                Локальный сервер: ключ не нужен, запросы никуда не уходят.
              </span>
            )}
          </label>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-slate-400">Модель</span>
              <button
                onClick={() => loadModels(settings.base_url)}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-cyan-200"
                title="Спросить у сервера, какие модели он отдаёт"
              >
                <RefreshCw className="h-3 w-3" /> Список моделей
              </button>
            </div>
            <input
              className="field"
              aria-label="Модель"
              value={settings.model_name}
              onChange={e => patch({ model_name: e.target.value })}
            />
            {models.length > 0 && (
              <select
                className="field"
                aria-label="Модели сервера"
                value={models.some(m => m.id === settings.model_name) ? settings.model_name : ''}
                onChange={e => patch({ model_name: e.target.value })}
              >
                <option value="">— выберите из моделей сервера —</option>
                {models.map(model => (
                  <option key={model.id} value={model.id}>
                    {model.id}
                    {model.state === 'loaded' ? ' • загружена' : ''}
                    {model.context ? ` • ${Math.round(model.context / 1024)}K` : ''}
                  </option>
                ))}
              </select>
            )}
          </div>

          <label className="space-y-1.5 md:col-span-2">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              API-ключ {settings.api_key_set && <span className="text-emerald-300">— сохранён ({settings.api_key})</span>}
            </span>
            <input
              className="field"
              type="password"
              value={apiKey}
              placeholder={
                isLocalUrl(settings.base_url)
                  ? 'Локальной модели ключ не требуется'
                  : settings.api_key_set ? 'Оставьте пустым, чтобы не менять' : 'sk-…'
              }
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

      {/* Голос */}
      <section className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Mic className="h-5 w-5 text-cyber-cyan" />
          <h2 className="font-semibold text-white">Голосовой режим</h2>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => save({ voice_enabled: !settings.voice_enabled })}
            className={`chip ${settings.voice_enabled ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
          >
            {settings.voice_enabled ? 'Слушает микрофон' : 'Микрофон не слушается'}
          </button>
          <button
            onClick={() => save({ live_mode: !settings.live_mode })}
            className={`chip ${settings.live_mode ? 'border-emerald-400/40 text-emerald-200' : 'text-slate-400'}`}
            title="После ответа можно говорить дальше без обращения по имени"
          >
            {settings.live_mode ? 'Живой диалог включён' : 'Живой диалог выключен'}
          </button>
          <button
            onClick={() => save({ barge_in: !settings.barge_in })}
            className={`chip ${settings.barge_in ? 'border-amber-400/40 text-amber-200' : 'text-slate-400'}`}
            title="Перебивать питомца голосом (работает, когда звук идёт в колонки ПК)"
          >
            {settings.barge_in ? 'Можно перебивать' : 'Перебивание выключено'}
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Окно живого диалога: {settings.conversation_window_sec} с
            </span>
            <input
              type="range"
              min={10}
              max={180}
              step={5}
              value={settings.conversation_window_sec}
              onChange={e => patch({ conversation_window_sec: Number(e.target.value) })}
              onMouseUp={() => save()}
              className="w-full accent-cyan-400"
            />
            <span className="block text-[11px] text-slate-500">
              Столько секунд после ответа можно продолжать разговор без «Патрик».
            </span>
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Пауза до конца фразы: {settings.endpoint_silence_sec.toFixed(1)} с
            </span>
            <input
              type="range"
              min={0.3}
              max={2}
              step={0.1}
              value={settings.endpoint_silence_sec}
              onChange={e => patch({ endpoint_silence_sec: Number(e.target.value) })}
              onMouseUp={() => save()}
              className="w-full accent-cyan-400"
            />
            <span className="block text-[11px] text-slate-500">
              Меньше — быстрее реакция, больше — не обрывает на раздумьях.
            </span>
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Чувствительность к речи: {settings.vad_sensitivity.toFixed(1)}×
            </span>
            <input
              type="range"
              min={1.5}
              max={6}
              step={0.1}
              value={settings.vad_sensitivity}
              onChange={e => patch({ vad_sensitivity: Number(e.target.value) })}
              onMouseUp={() => save()}
              className="w-full accent-cyan-400"
            />
            <span className="block text-[11px] text-slate-500">
              Во сколько раз голос должен быть громче фонового шума комнаты.
            </span>
          </label>

          <label className="space-y-1.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">
              Порог тишины: {settings.vad_min_level.toFixed(3)}
            </span>
            <input
              type="range"
              min={0.004}
              max={0.06}
              step={0.002}
              value={settings.vad_min_level}
              onChange={e => patch({ vad_min_level: Number(e.target.value) })}
              onMouseUp={() => save()}
              className="w-full accent-cyan-400"
            />
            <span className="block text-[11px] text-slate-500">
              Поднимите, если питомец реагирует на шум вентиляторов.
            </span>
          </label>
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-slate-400">Движок распознавания</div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => save({ stt_engine: 'vosk' })}
              className={`chip ${settings.stt_engine === 'vosk' ? 'border-cyber-cyan/60 text-cyan-200' : 'text-slate-300'}`}
            >
              Vosk — офлайн, без ключей
            </button>
            <button
              onClick={() => save({ stt_engine: 'whisper' })}
              className={`chip ${settings.stt_engine === 'whisper' ? 'border-cyber-cyan/60 text-cyan-200' : 'text-slate-300'}`}
            >
              Whisper API — точнее, нужен ключ
            </button>
          </div>

          {settings.stt_engine === 'whisper' && (
            <div className="grid gap-3 md:grid-cols-3">
              <input
                className="field"
                placeholder="https://api.openai.com/v1"
                value={settings.stt_base_url}
                onChange={e => patch({ stt_base_url: e.target.value })}
              />
              <input
                className="field"
                placeholder="whisper-1"
                value={settings.stt_model}
                onChange={e => patch({ stt_model: e.target.value })}
              />
              <input
                className="field"
                type="password"
                placeholder={settings.stt_api_key_set ? 'ключ сохранён' : 'ключ для распознавания'}
                value={sttKey}
                onChange={e => setSttKey(e.target.value)}
              />
            </div>
          )}
        </div>

        <button onClick={() => save(sttKey.trim() ? { stt_api_key: sttKey.trim() } as Partial<Settings> : {})} className="btn-primary w-fit">
          <Save className="h-4 w-4" /> Сохранить
        </button>
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

      {/* Программа */}
      <section className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Download className="h-5 w-5 text-cyber-cyan" />
          <h2 className="font-semibold text-white">Программа</h2>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-300">
          <span>
            Версия <span className="font-mono text-white">{update?.current ?? '—'}</span>
          </span>
          {update?.from_sources && (
            <span className="text-xs text-slate-500">запуск из исходников — обновление через git</span>
          )}
        </div>

        {update?.available ? (
          <div className="space-y-2 rounded-xl border border-emerald-400/30 bg-emerald-400/5 p-4">
            <div className="text-sm font-semibold text-emerald-200">
              Доступна версия {update.available.version}
              {update.available.size > 0 && (
                <span className="ml-2 font-normal text-slate-400">
                  {Math.round(update.available.size / 1048576)} МБ
                </span>
              )}
            </div>
            {update.available.notes && (
              <p className="max-h-32 overflow-y-auto whitespace-pre-line text-xs leading-relaxed text-slate-300">
                {update.available.notes}
              </p>
            )}
            {update.downloading && (
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full bg-cyber-cyan transition-all"
                  style={{ width: `${update.progress}%` }}
                />
              </div>
            )}
            <div className="flex flex-wrap gap-3 pt-1">
              {update.installable ? (
                <button onClick={installUpdate} disabled={update.downloading} className="btn-primary">
                  <Download className="h-4 w-4" />
                  {update.downloading ? `Скачиваю… ${update.progress}%` : `Обновить до ${update.available.version}`}
                </button>
              ) : (
                <a href={update.available.page} target="_blank" rel="noreferrer" className="btn-ghost">
                  Открыть страницу релиза
                </a>
              )}
            </div>
          </div>
        ) : (
          <p className="text-xs text-slate-400">
            {update?.last_error
              ? `Последняя проверка не удалась: ${update.last_error}`
              : 'Обновлений нет — установлена последняя версия.'}
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <button onClick={checkUpdate} className="btn-ghost">
            <RefreshCw className="h-4 w-4 text-cyber-cyan" /> Проверить обновления
          </button>
          <button
            onClick={() => save({ auto_check_updates: !settings.auto_check_updates })}
            className={`chip ${settings.auto_check_updates ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
          >
            {settings.auto_check_updates ? 'Проверяет обновления сам' : 'Проверять только вручную'}
          </button>
          <button
            onClick={() => save({ panel_window: !settings.panel_window })}
            className={`chip ${settings.panel_window ? 'border-cyber-cyan/50 text-cyan-200' : 'text-slate-400'}`}
            title="Из трея панель открывается в отдельном окне приложения"
          >
            <AppWindow className="h-3.5 w-3.5" />
            {settings.panel_window ? 'Открывать в своём окне' : 'Открывать в браузере'}
          </button>
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
