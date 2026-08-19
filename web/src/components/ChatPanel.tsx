import React, { useEffect, useRef, useState } from 'react';
import { Eraser, Send, Sparkles } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

const QUICK_TASKS = [
  'Что сейчас грузит мой компьютер?',
  'Покажи статус git в моём проекте',
  'Напомни через 25 минут сделать перерыв',
  'Закрой всё, что жрёт память',
];

export const ChatPanel: React.FC = () => {
  const chatHistory = useAppStore(state => state.chatHistory);
  const agentStatus = useAppStore(state => state.agentStatus);
  const isConnected = useAppStore(state => state.isConnected);
  const sendTask = useAppStore(state => state.sendTask);
  const resetChat = useAppStore(state => state.resetChat);

  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [chatHistory, agentStatus.state]);

  const submit = (text: string) => {
    if (!text.trim() || !isConnected) return;
    sendTask(text);
    setDraft('');
  };

  const busy = agentStatus.state !== 'idle';

  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <header className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-cyber-cyan" />
          <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-300">Диалог</h3>
        </div>
        <button
          onClick={resetChat}
          className="chip text-slate-400 hover:text-white"
          title="Очистить историю и память диалога"
        >
          <Eraser className="h-3.5 w-3.5" /> Очистить
        </button>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {chatHistory.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="max-w-sm text-sm text-slate-400">
              Скажите «Атом, …» в микрофон питомца или напишите задачу здесь — он выполнит её сам.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {QUICK_TASKS.map(task => (
                <button
                  key={task}
                  onClick={() => submit(task)}
                  disabled={!isConnected}
                  className="chip text-slate-300 hover:border-cyber-cyan/60 hover:text-white disabled:opacity-40"
                >
                  {task}
                </button>
              ))}
            </div>
          </div>
        ) : (
          chatHistory.map((message, index) => (
            <div
              key={`${message.id}-${index}`}
              className={`flex flex-col ${message.sender === 'user' ? 'items-end' : 'items-start'}`}
            >
              <span className="mb-1 px-1 text-[11px] font-medium tracking-wide text-slate-500">
                {message.sender === 'user' ? 'ВЫ' : 'АТОМ'}
              </span>
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  message.sender === 'user'
                    ? 'rounded-tr-sm bg-cyber-cyan/15 text-cyan-100'
                    : 'rounded-tl-sm border border-white/5 bg-white/5 text-slate-100'
                } ${message.isPartial ? 'opacity-60' : ''}`}
              >
                {message.text}
              </div>
            </div>
          ))
        )}

        {busy && (
          <div className="flex items-center gap-2 px-1 text-xs text-slate-400">
            <span className="flex gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyber-cyan" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyber-cyan" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyber-cyan" />
            </span>
            {agentStatus.state === 'working' && agentStatus.tool
              ? `Выполняю: ${agentStatus.tool}`
              : agentStatus.state === 'speaking'
                ? 'Говорю…'
                : 'Думаю…'}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(draft);
        }}
        className="flex gap-2 border-t border-white/5 p-3"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={!isConnected}
          placeholder={isConnected ? 'Поставьте задачу Атому…' : 'Нет связи с сервером'}
          className="field flex-1"
        />
        <button type="submit" disabled={!isConnected || !draft.trim()} className="btn-primary px-4">
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
};

export default ChatPanel;
