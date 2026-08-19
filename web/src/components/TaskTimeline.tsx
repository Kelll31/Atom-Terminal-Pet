import React, { useState } from 'react';
import {
  AlertTriangle, Ban, Brain, CheckCircle2, ChevronDown, ChevronRight, Clock, Loader2, Wrench,
} from 'lucide-react';
import type { Task, TaskStep } from '../store/useAppStore';
import { useAppStore } from '../store/useAppStore';

const STATUS_META: Record<Task['status'], { label: string; className: string; icon: React.ReactNode }> = {
  queued:           { label: 'в очереди',    className: 'text-slate-300 border-white/10 bg-white/5',        icon: <Clock className="h-3.5 w-3.5" /> },
  running:          { label: 'выполняется',  className: 'text-cyan-200 border-cyan-400/30 bg-cyan-400/10',  icon: <Loader2 className="h-3.5 w-3.5 animate-spin" /> },
  waiting_approval: { label: 'ждёт ответа',  className: 'text-amber-200 border-amber-400/30 bg-amber-400/10', icon: <AlertTriangle className="h-3.5 w-3.5" /> },
  done:             { label: 'готово',       className: 'text-emerald-200 border-emerald-400/30 bg-emerald-400/10', icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  failed:           { label: 'ошибка',       className: 'text-red-200 border-red-400/30 bg-red-400/10',     icon: <AlertTriangle className="h-3.5 w-3.5" /> },
  cancelled:        { label: 'отменено',     className: 'text-slate-400 border-white/10 bg-white/5',        icon: <Ban className="h-3.5 w-3.5" /> },
};

const StepRow: React.FC<{ step: TaskStep }> = ({ step }) => {
  const [open, setOpen] = useState(false);

  if (step.type === 'thought') {
    return (
      <div className="flex gap-2 py-1.5 text-sm text-slate-300">
        <Brain className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" />
        <span className="whitespace-pre-wrap">{step.text}</span>
      </div>
    );
  }

  if (step.type === 'tool_call') {
    const args = Object.entries(step.args ?? {})
      .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
      .join(', ');
    return (
      <div className="flex gap-2 py-1.5 text-sm">
        <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-cyber-cyan" />
        <div className="min-w-0">
          <span className="font-mono text-cyber-cyan">{step.tool}</span>
          {args && (
            <span className="ml-2 break-all font-mono text-xs text-slate-400">({args.slice(0, 220)})</span>
          )}
        </div>
      </div>
    );
  }

  const failed = !step.ok;
  return (
    <div className="py-1">
      <button
        onClick={() => setOpen(v => !v)}
        className={`flex w-full items-start gap-2 text-left text-sm ${failed ? 'text-red-300' : 'text-emerald-200'}`}
      >
        {open ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0" />}
        <span className="min-w-0 flex-1 truncate">
          {failed ? 'Ошибка: ' : 'Результат: '}
          <span className="text-slate-400">{step.result.split('\n')[0].slice(0, 120)}</span>
        </span>
      </button>
      {open && (
        <pre className="ml-6 mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-white/10 bg-black/40 p-3 font-mono text-[11px] text-slate-300">
          {step.result}
        </pre>
      )}
    </div>
  );
};

export const TaskCard: React.FC<{ task: Task; defaultOpen?: boolean }> = ({ task, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  const cancelTask = useAppStore(state => state.cancelTask);
  const meta = STATUS_META[task.status];
  const active = task.status === 'running' || task.status === 'waiting_approval' || task.status === 'queued';

  return (
    <div className="card overflow-hidden">
      <div className="flex items-start gap-3 p-4">
        <button onClick={() => setOpen(v => !v)} className="mt-0.5 text-slate-400 hover:text-white">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${meta.className}`}>
              {meta.icon} {meta.label}
            </span>
            <span className="text-[11px] uppercase tracking-wider text-slate-500">
              {task.source === 'voice' ? 'голос' : task.source === 'rule' ? 'правило' : 'панель'} · {task.duration}с
            </span>
          </div>
          <p className="mt-1.5 text-sm font-medium text-white">{task.title}</p>
          {task.result && <p className="mt-1 text-sm text-slate-300">{task.result}</p>}
          {task.error && <p className="mt-1 text-sm text-red-300">{task.error}</p>}
        </div>

        {active && (
          <button onClick={() => cancelTask(task.id)} className="chip text-slate-400 hover:text-red-300">
            <Ban className="h-3.5 w-3.5" /> Стоп
          </button>
        )}
      </div>

      {open && task.steps.length > 0 && (
        <div className="border-t border-white/5 bg-black/20 px-4 py-2">
          {task.steps.map(step => (
            <StepRow key={step.id} step={step} />
          ))}
        </div>
      )}
    </div>
  );
};

export const TaskTimeline: React.FC<{ tasks: Task[]; emptyHint?: string }> = ({ tasks, emptyHint }) => {
  if (tasks.length === 0) {
    return (
      <div className="card flex items-center justify-center p-8 text-sm text-slate-500">
        {emptyHint ?? 'Задач пока не было.'}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {tasks.map((task, index) => (
        <TaskCard key={task.id} task={task} defaultOpen={index === 0 && task.status !== 'done'} />
      ))}
    </div>
  );
};

export default TaskTimeline;
