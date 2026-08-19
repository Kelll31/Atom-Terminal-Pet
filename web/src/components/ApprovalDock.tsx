import React from 'react';
import { ShieldAlert, Check, CheckCheck, X } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

const RISK_STYLES: Record<string, { label: string; className: string }> = {
  safe: { label: 'безопасно', className: 'text-emerald-300 border-emerald-400/40 bg-emerald-400/10' },
  caution: { label: 'осторожно', className: 'text-amber-300 border-amber-400/40 bg-amber-400/10' },
  danger: { label: 'опасно', className: 'text-red-300 border-red-400/40 bg-red-400/10' },
};

/** Всплывающие запросы подтверждения опасных действий агента. */
export const ApprovalDock: React.FC = () => {
  const approvals = useAppStore(state => state.approvals);
  const resolveApproval = useAppStore(state => state.resolveApproval);

  if (approvals.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,26rem)] flex-col gap-3">
      {approvals.map(approval => {
        const risk = RISK_STYLES[approval.risk] ?? RISK_STYLES.caution;
        return (
          <div
            key={approval.id}
            className="pointer-events-auto animate-fade-in rounded-2xl border border-amber-400/30 bg-cyber-navy/95 p-4 shadow-2xl backdrop-blur"
          >
            <div className="mb-2 flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-amber-300" />
              <span className="text-sm font-semibold text-white">Разрешить действие?</span>
              <span className={`ml-auto rounded-full border px-2 py-0.5 text-[11px] ${risk.className}`}>
                {risk.label}
              </span>
            </div>

            <p className="mb-2 text-xs text-slate-400">Задача: {approval.task_title}</p>

            <div className="mb-3 rounded-lg border border-white/10 bg-black/40 p-3">
              <div className="font-mono text-sm text-cyber-cyan">{approval.tool}</div>
              <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-slate-300">
                {JSON.stringify(approval.args, null, 2)}
              </pre>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => resolveApproval(approval.id, 'allow')}
                className="btn-primary flex-1"
              >
                <Check className="h-4 w-4" /> Разрешить
              </button>
              <button
                onClick={() => resolveApproval(approval.id, 'allow_always')}
                className="btn-ghost"
                title="Больше не спрашивать про этот инструмент до перезапуска сервера"
              >
                <CheckCheck className="h-4 w-4" /> Всегда
              </button>
              <button onClick={() => resolveApproval(approval.id, 'deny')} className="btn-danger">
                <X className="h-4 w-4" /> Нет
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ApprovalDock;
