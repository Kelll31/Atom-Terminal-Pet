import React, { useState, useEffect, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import { Terminal, MessageSquare, Gamepad2, Send } from 'lucide-react';

const DebugPage: React.FC = () => {
  const { isConnected, logs, sendMessage } = useAppStore();
  const [speechText, setSpeechText] = useState('');
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleSendEmotion = (emotion: string) => {
    sendMessage({ action: 'speak', emotion, text: '' });
  };

  const handleSendSpeech = (e: React.FormEvent) => {
    e.preventDefault();
    if (!speechText.trim()) return;
    sendMessage({ action: 'speak', emotion: 'idle', text: speechText });
    setSpeechText('');
  };

  return (
    <div className="flex-1 p-8 max-w-6xl mx-auto w-full animate-fade-in grid grid-cols-1 lg:grid-cols-3 gap-8">
      
      {/* Control Panel */}
      <div className="lg:col-span-1 space-y-8">
        <div>
          <h2 className="text-3xl font-bold flex items-center gap-2 mb-2">
            <Gamepad2 className="w-8 h-8 text-cyber-cyan" />
            Remote Control
          </h2>
          <p className="text-gray-400 text-sm">Manually override pet behavior.</p>
        </div>

        {/* Emotion Override */}
        <div className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-xl space-y-4">
          <h3 className="text-sm font-bold text-cyber-cyan uppercase tracking-wider">Manual Emotion Override</h3>
          <div className="grid grid-cols-2 gap-2.5">
            {['happy', 'angry', 'sleepy', 'panic', 'idle', 'love', 'dizzy', 'sad'].map(emotion => (
              <button
                key={emotion}
                disabled={!isConnected}
                onClick={() => handleSendEmotion(emotion)}
                className="px-3 py-2 bg-cyber-dark border border-gray-700 hover:border-cyber-cyan hover:text-cyber-cyan rounded capitalize text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {emotion}
              </button>
            ))}
          </div>
        </div>

        {/* Wake Word / Pet Name Test */}
        <div className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-xl space-y-4">
          <h3 className="text-sm font-bold text-yellow-400 uppercase tracking-wider">Проверка клички ("Атом" / "Микро")</h3>
          <div className="flex flex-col gap-2">
            <button
              disabled={!isConnected}
              onClick={() => sendMessage({ action: 'user_text', text: 'Атом!' })}
              className="w-full py-2 bg-cyber-dark border border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10 rounded text-xs transition-colors disabled:opacity-50"
            >
              Позвать: "Атом!"
            </button>
            <button
              disabled={!isConnected}
              onClick={() => sendMessage({ action: 'user_text', text: 'Микро!' })}
              className="w-full py-2 bg-cyber-dark border border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10 rounded text-xs transition-colors disabled:opacity-50"
            >
              Позвать: "Микро!"
            </button>
            <button
              disabled={!isConnected}
              onClick={() => sendMessage({ action: 'user_text', text: 'Микро, как дела?' })}
              className="w-full py-2 bg-cyber-dark border border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10 rounded text-xs transition-colors disabled:opacity-50"
            >
              Спросить: "Микро, как дела?"
            </button>
          </div>
        </div>

        {/* Speech Bubble */}
        <div className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-xl space-y-4">
          <h3 className="text-sm font-bold text-cyber-emerald uppercase tracking-wider flex items-center gap-2">
            <MessageSquare className="w-4 h-4" />
            Send Speech Bubble
          </h3>
          <form onSubmit={handleSendSpeech} className="flex gap-2">
            <input
              type="text"
              value={speechText}
              onChange={(e) => setSpeechText(e.target.value)}
              disabled={!isConnected}
              placeholder="Type message..."
              className="flex-1 bg-cyber-dark border border-gray-700 rounded px-3 py-2 outline-none focus:border-cyber-emerald disabled:opacity-50 text-sm"
            />
            <button 
              type="submit"
              disabled={!isConnected || !speechText.trim()}
              className="px-3 py-2 bg-cyber-emerald/20 text-cyber-emerald border border-cyber-emerald rounded hover:bg-cyber-emerald/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* Live Logs Terminal */}
      <div className="lg:col-span-2 flex flex-col h-[600px] bg-[#0c0c0c] border border-gray-800 rounded-xl overflow-hidden shadow-2xl relative">
        <div className="bg-[#1a1a1a] p-3 border-b border-gray-800 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-gray-400" />
          <span className="text-xs text-gray-400 font-mono tracking-widest uppercase">System Logs [Live]</span>
          <div className="ml-auto flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
            <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 font-mono text-sm space-y-1">
          {logs.length === 0 ? (
            <div className="text-gray-600 italic">No logs yet. Waiting for WebSocket messages...</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="break-all">
                <span className="text-gray-500">[{new Date().toLocaleTimeString()}]</span>{' '}
                <span className={
                  log.includes('System') ? 'text-cyber-cyan' :
                  log.includes('Agent') ? 'text-cyber-emerald' :
                  'text-gray-300'
                }>
                  {log}
                </span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

    </div>
  );
};

export default DebugPage;
