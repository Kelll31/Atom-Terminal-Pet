import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, Play, Plug, Plus, RefreshCw, ScrollText, Server, Trash2, Wrench,
} from 'lucide-react';
import { API_BASE } from '../config';

interface Tool {
  name: string;
  description: string;
  risk: 'safe' | 'caution' | 'danger';
  category: string;
  source: string;
  enabled: boolean;
}

interface MCPServer {
  name: string;
  command: string;
  args: string[];
  enabled: boolean;
  description: string;
  status: 'ready' | 'starting' | 'error' | 'stopped' | 'disabled';
  error: string;
  tools: string[];
}

interface AuditEntry {
  ts: string;
  tool: string;
  args: Record<string, unknown>;
  status: string;
  duration_ms: number;
  result: string;
}

const RISK_BADGE: Record<Tool['risk'], string> = {
  safe: 'border-emerald-400/30 text-emerald-200',
  caution: 'border-amber-400/30 text-amber-200',
  danger: 'border-red-400/30 text-red-200',
};

const RISK_LABEL: Record<Tool['risk'], string> = {
  safe: 'безопасный',
  caution: 'осторожно',
  danger: 'опасный',
};

const STATUS_BADGE: Record<MCPServer['status'], string> = {
  ready: 'border-emerald-400/30 text-emerald-200',
  starting: 'border-cyan-400/30 text-cyan-200',
  error: 'border-red-400/30 text-red-200',
  stopped: 'border-white/10 text-slate-300',
  disabled: 'border-white/10 text-slate-500',
};

const ToolsPage: React.FC = () => {
  const [tools, setTools] = useState<Tool[]>([]);
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [testResult, setTestResult] = useState<{ tool: string; text: string } | null>(null);

  const [draft, setDraft] = useState({ name: '', command: 'npx', args: '', description: '' });

  const load = useCallback(async () => {
    try {
      const [toolsRes, serversRes, auditRes] = await Promise.all([
        fetch(`${API_BASE}/api/tools`),
        fetch(`${API_BASE}/api/mcp/servers`),
        fetch(`${API_BASE}/api/audit?limit=40`),
      ]);
      setTools((await toolsRes.json()).tools ?? []);
      setServers((await serversRes.json()).servers ?? []);
      setAudit((await auditRes.json()).entries ?? []);
    } catch {
      setNotice('Не удалось связаться с сервером Атома.');
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const toggleTool = async (tool: Tool) => {
    await fetch(`${API_BASE}/api/tools/${encodeURIComponent(tool.name)}/toggle?enabled=${!tool.enabled}`, {
      method: 'POST',
    });
    load();
  };

  const runTool = async (tool: Tool) => {
    setTestResult({ tool: tool.name, text: 'Выполняю…' });
    try {
      const res = await fetch(`${API_BASE}/api/tools/${encodeURIComponent(tool.name)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ args: {} }),
      });
      const data = await res.json();
      setTestResult({ tool: tool.name, text: data.result ?? JSON.stringify(data) });
    } catch (error) {
      setTestResult({ tool: tool.name, text: String(error) });
    }
  };

  const addServer = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim() || !draft.command.trim()) return;
    setBusy(true);
    setNotice('');
    try {
      const res = await fetch(`${API_BASE}/api/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: draft.name.trim(),
          command: draft.command.trim(),
          args: draft.args.split(/\s+/).filter(Boolean),
          description: draft.description.trim(),
          enabled: true,
        }),
      });
      const data = await res.json();
      setNotice(
        data.server?.status === 'ready'
          ? `Сервер «${data.server.name}» запущен, инструментов: ${data.server.tools.length}`
          : `Сервер добавлен, но не запустился: ${data.server?.error || 'нет данных'}`,
      );
      setDraft({ name: '', command: 'npx', args: '', description: '' });
      load();
    } catch (error) {
      setNotice(`Ошибка: ${error}`);
    } finally {
      setBusy(false);
    }
  };

  const serverAction = async (name: string, action: 'restart' | 'delete' | 'toggle', enabled?: boolean) => {
    setBusy(true);
    try {
      if (action === 'delete') {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' });
      } else if (action === 'restart') {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(name)}/restart`, { method: 'POST' });
      } else {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(name)}/toggle?enabled=${enabled}`, {
          method: 'POST',
        });
      }
      await load();
    } finally {
      setBusy(false);
    }
  };

  const grouped = tools.reduce<Record<string, Tool[]>>((acc, tool) => {
    (acc[tool.category] ??= []).push(tool);
    return acc;
  }, {});

  return (
    <div className="animate-fade-in mx-auto w-full max-w-6xl space-y-8 p-4 md:p-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Инструменты и MCP</h1>
        <p className="mt-1 text-sm text-slate-400">
          Всё, чем Атом может пользоваться на вашем компьютере. Ненужное можно выключить,
          а внешние MCP-серверы — подключить в один клик.
        </p>
      </header>

      {notice && (
        <div className="card flex items-center gap-2 p-3 text-sm text-slate-200">
          <CheckCircle2 className="h-4 w-4 text-cyber-cyan" /> {notice}
        </div>
      )}

      {/* MCP-серверы */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
          <Server className="h-4 w-4" /> MCP-серверы
        </h2>

        <div className="grid gap-3 md:grid-cols-2">
          {servers.map(server => (
            <div key={server.name} className="card space-y-3 p-4">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-white">{server.name}</span>
                <span className={`chip ${STATUS_BADGE[server.status]}`}>{server.status}</span>
                <div className="ml-auto flex gap-1">
                  <button
                    onClick={() => serverAction(server.name, 'toggle', !server.enabled)}
                    disabled={busy}
                    className="chip text-slate-300 hover:text-white"
                  >
                    <Plug className="h-3.5 w-3.5" /> {server.enabled ? 'Выкл' : 'Вкл'}
                  </button>
                  <button
                    onClick={() => serverAction(server.name, 'restart')}
                    disabled={busy}
                    className="chip text-slate-300 hover:text-white"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => serverAction(server.name, 'delete')}
                    disabled={busy}
                    className="chip text-slate-400 hover:text-red-300"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {server.description && <p className="text-xs text-slate-400">{server.description}</p>}
              <p className="font-mono text-[11px] text-slate-500">
                {server.command} {server.args.join(' ')}
              </p>

              {server.error && (
                <p className="flex items-start gap-1.5 text-xs text-red-300">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {server.error}
                </p>
              )}

              {server.tools.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {server.tools.map(tool => (
                    <span key={tool} className="chip text-[11px] text-cyan-200">{tool}</span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {/* Добавление сервера */}
          <form onSubmit={addServer} className="card space-y-2 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Plus className="h-4 w-4 text-cyber-cyan" /> Добавить MCP-сервер
            </div>
            <input
              className="field"
              placeholder="Имя, например filesystem"
              value={draft.name}
              onChange={e => setDraft({ ...draft, name: e.target.value })}
            />
            <input
              className="field"
              placeholder="Команда: npx / node / python"
              value={draft.command}
              onChange={e => setDraft({ ...draft, command: e.target.value })}
            />
            <input
              className="field"
              placeholder="Аргументы через пробел: -y @modelcontextprotocol/server-filesystem D:/projects"
              value={draft.args}
              onChange={e => setDraft({ ...draft, args: e.target.value })}
            />
            <input
              className="field"
              placeholder="Описание (необязательно)"
              value={draft.description}
              onChange={e => setDraft({ ...draft, description: e.target.value })}
            />
            <button type="submit" disabled={busy} className="btn-primary w-full">
              {busy ? 'Подключаю…' : 'Подключить'}
            </button>
            <p className="text-[11px] leading-relaxed text-slate-500">
              Сервер запускается сразу — если он не поднимется, увидите ошибку прямо здесь.
            </p>
          </form>
        </div>
      </section>

      {/* Инструменты */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
          <Wrench className="h-4 w-4" /> Инструменты ({tools.length})
        </h2>

        {Object.entries(grouped).map(([category, items]) => (
          <div key={category} className="card overflow-hidden">
            <div className="border-b border-white/5 px-4 py-2 text-xs uppercase tracking-wider text-slate-400">
              {category}
            </div>
            <div className="divide-y divide-white/5">
              {items.map(tool => (
                <div key={tool.name} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-white">{tool.name}</span>
                      <span className={`chip ${RISK_BADGE[tool.risk]} text-[10px]`}>{RISK_LABEL[tool.risk]}</span>
                      {tool.source !== 'local' && (
                        <span className="chip text-[10px] text-violet-200">{tool.source}</span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-slate-400">{tool.description}</p>
                  </div>

                  {tool.risk === 'safe' && (
                    <button onClick={() => runTool(tool)} className="chip text-slate-300 hover:text-white">
                      <Play className="h-3.5 w-3.5" /> Проверить
                    </button>
                  )}

                  <button
                    onClick={() => toggleTool(tool)}
                    className={`chip ${tool.enabled ? 'border-emerald-400/30 text-emerald-200' : 'text-slate-500'}`}
                  >
                    {tool.enabled ? 'включён' : 'выключен'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {testResult && (
        <div className="card space-y-2 p-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-sm text-cyber-cyan">{testResult.tool}</span>
            <button onClick={() => setTestResult(null)} className="chip text-slate-400">Закрыть</button>
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-black/40 p-3 font-mono text-xs text-slate-300">
            {testResult.text}
          </pre>
        </div>
      )}

      {/* Журнал */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
          <ScrollText className="h-4 w-4" /> Журнал действий
        </h2>
        <div className="card divide-y divide-white/5 overflow-hidden">
          {audit.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">Атом ещё ничего не запускал.</p>
          ) : (
            audit.map((entry, index) => (
              <div key={`${entry.ts}-${index}`} className="flex flex-wrap items-center gap-2 px-4 py-2 text-xs">
                <span className="text-slate-500">{entry.ts}</span>
                <span className="font-mono text-cyber-cyan">{entry.tool}</span>
                <span className={entry.status === 'ok' ? 'text-emerald-300' : 'text-red-300'}>{entry.status}</span>
                <span className="text-slate-500">{entry.duration_ms} мс</span>
                <span className="w-full truncate text-slate-400 md:w-auto md:flex-1">{entry.result}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
};

export default ToolsPage;
