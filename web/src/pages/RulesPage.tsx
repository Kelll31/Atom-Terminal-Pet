import React, { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Plus, Save, SlidersHorizontal, Trash2, Zap } from 'lucide-react';
import { API_BASE } from '../config';

interface Rule {
  id: string;
  description: string;
  condition: {
    metric: string;
    operator: string;
    value: number;
    duration_seconds: number;
  };
  action: {
    type: 'set_emotion' | 'speak' | 'agent_task';
    emotion: string;
    text: string;
    task?: string;
  };
  cooldown_seconds: number;
}

const METRICS = [
  { value: 'cpu', label: 'Загрузка CPU, %' },
  { value: 'ram', label: 'Загрузка RAM, %' },
  { value: 'gpu', label: 'Загрузка GPU, %' },
  { value: 'temp', label: 'Температура, °C' },
];

const EMOTIONS = ['idle', 'happy', 'angry', 'sad', 'love', 'dizzy', 'sleepy', 'working', 'thinking', 'panic', 'sweat', 'party'];

const ACTION_TYPES = [
  { value: 'set_emotion', label: 'Показать эмоцию' },
  { value: 'speak', label: 'Сказать вслух' },
  { value: 'agent_task', label: 'Поставить задачу агенту' },
];

const RulesPage: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/rules`)
      .then(res => res.json())
      .then(data => setRules(data.rules ?? []))
      .catch(() => setStatus('Не удалось загрузить правила.'))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setStatus('Сохраняю…');
    try {
      const res = await fetch(`${API_BASE}/api/rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const data = await res.json();
      setStatus(`Сохранено, правил активно: ${data.count ?? rules.length}`);
    } catch (error) {
      setStatus(`Ошибка сохранения: ${error}`);
    }
  };

  const update = (id: string, path: string, value: unknown) => {
    setRules(current =>
      current.map(rule => {
        if (rule.id !== id) return rule;
        const [head, tail] = path.split('.');
        if (!tail) return { ...rule, [head]: value } as Rule;
        return { ...rule, [head]: { ...(rule as any)[head], [tail]: value } } as Rule;
      }),
    );
  };

  const addRule = () =>
    setRules(current => [
      ...current,
      {
        id: `rule_${Date.now()}`,
        description: 'Новое правило',
        condition: { metric: 'cpu', operator: '>', value: 85, duration_seconds: 30 },
        action: { type: 'set_emotion', emotion: 'panic', text: 'CPU!' },
        cooldown_seconds: 600,
      },
    ]);

  if (loading) return <div className="p-8 text-sm text-slate-400">Загружаю правила…</div>;

  return (
    <div className="animate-fade-in mx-auto w-full max-w-5xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <SlidersHorizontal className="h-6 w-6 text-cyber-cyan" /> Правила поведения
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Питомец сам реагирует на состояние компьютера: меняет настроение, говорит или берётся за задачу.
          </p>
        </div>
        <button onClick={save} className="btn-primary">
          <Save className="h-4 w-4" /> Сохранить и применить
        </button>
      </header>

      {status && (
        <div className="card flex items-center gap-2 p-3 text-sm text-slate-200">
          <CheckCircle2 className="h-4 w-4 text-cyber-cyan" /> {status}
        </div>
      )}

      <div className="space-y-4">
        {rules.map(rule => (
          <div key={rule.id} className="card space-y-4 p-5">
            <div className="flex items-center gap-3">
              <input
                value={rule.description}
                onChange={e => update(rule.id, 'description', e.target.value)}
                className="flex-1 border-b border-transparent bg-transparent text-lg font-semibold text-white outline-none transition-colors focus:border-cyber-cyan"
              />
              <button
                onClick={() => setRules(current => current.filter(r => r.id !== rule.id))}
                className="text-slate-500 transition-colors hover:text-red-300"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="grid gap-5 rounded-xl border border-white/5 bg-black/25 p-4 md:grid-cols-2">
              <div className="space-y-3">
                <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyber-cyan">
                  <Activity className="h-4 w-4" /> Если
                </h3>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={rule.condition.metric}
                    onChange={e => update(rule.id, 'condition.metric', e.target.value)}
                    className="field w-auto"
                  >
                    {METRICS.map(metric => (
                      <option key={metric.value} value={metric.value} className="bg-cyber-dark">
                        {metric.label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={rule.condition.operator}
                    onChange={e => update(rule.id, 'condition.operator', e.target.value)}
                    className="field w-16"
                  >
                    {['>', '<', '>=', '<=', '=='].map(op => (
                      <option key={op} value={op} className="bg-cyber-dark">{op}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={rule.condition.value}
                    onChange={e => update(rule.id, 'condition.value', Number(e.target.value))}
                    className="field w-24"
                  />
                </div>
                <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
                  держится
                  <input
                    type="number"
                    value={rule.condition.duration_seconds}
                    onChange={e => update(rule.id, 'condition.duration_seconds', Number(e.target.value))}
                    className="field w-20 text-center"
                  />
                  сек, повтор не чаще
                  <input
                    type="number"
                    value={rule.cooldown_seconds ?? 300}
                    onChange={e => update(rule.id, 'cooldown_seconds', Number(e.target.value))}
                    className="field w-24 text-center"
                  />
                  сек
                </div>
              </div>

              <div className="space-y-3">
                <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-300">
                  <Zap className="h-4 w-4" /> То
                </h3>

                <select
                  value={rule.action.type}
                  onChange={e => update(rule.id, 'action.type', e.target.value)}
                  className="field"
                >
                  {ACTION_TYPES.map(type => (
                    <option key={type.value} value={type.value} className="bg-cyber-dark">
                      {type.label}
                    </option>
                  ))}
                </select>

                {rule.action.type !== 'agent_task' && (
                  <select
                    value={rule.action.emotion}
                    onChange={e => update(rule.id, 'action.emotion', e.target.value)}
                    className="field"
                  >
                    {EMOTIONS.map(emotion => (
                      <option key={emotion} value={emotion} className="bg-cyber-dark">{emotion}</option>
                    ))}
                  </select>
                )}

                <input
                  value={rule.action.type === 'agent_task' ? (rule.action.task ?? rule.action.text) : rule.action.text}
                  onChange={e =>
                    update(rule.id, rule.action.type === 'agent_task' ? 'action.task' : 'action.text', e.target.value)
                  }
                  placeholder={
                    rule.action.type === 'agent_task'
                      ? 'Например: найди процесс, который грузит CPU, и предложи что закрыть'
                      : 'Что показать или сказать'
                  }
                  className="field"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={addRule}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-white/10 p-4 text-sm text-slate-400 transition-colors hover:border-cyber-cyan/50 hover:text-cyan-200"
      >
        <Plus className="h-4 w-4" /> Добавить правило
      </button>
    </div>
  );
};

export default RulesPage;
