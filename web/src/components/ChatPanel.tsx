import React, { useEffect, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';

export const ChatPanel: React.FC = () => {
  const chatHistory = useAppStore(state => state.chatHistory);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  return (
    <div className="flex flex-col h-full bg-cyber-navy/40 border border-cyber-navy rounded-xl overflow-hidden relative">
      <div className="bg-cyber-navy/60 px-4 py-3 border-b border-cyber-navy flex justify-between items-center">
        <h3 className="text-sm text-gray-300 uppercase tracking-widest font-bold">Live Transcript</h3>
        <span className="flex h-3 w-3 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyber-emerald opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-cyber-emerald"></span>
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-500 italic text-sm">
            No conversation yet. Speak to Atom!
          </div>
        ) : (
          chatHistory.map((msg, i) => (
            <div 
              key={`${msg.id}-${i}`} 
              className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'} max-w-full`}
            >
              <div className={`text-xs mb-1 text-gray-500 font-medium tracking-wide ${msg.sender === 'user' ? 'mr-1' : 'ml-1'}`}>
                {msg.sender === 'user' ? 'YOU' : 'ATOM'}
              </div>
              <div 
                className={`px-4 py-2 rounded-2xl max-w-[85%] text-sm ${
                  msg.sender === 'user' 
                    ? 'bg-cyber-cyan/20 text-cyber-cyan rounded-tr-none' 
                    : 'bg-cyber-dark text-gray-200 border border-cyber-navy rounded-tl-none'
                } ${msg.isPartial ? 'opacity-60 animate-pulse' : ''}`}
              >
                {msg.text || (msg.isPartial ? '...' : '')}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
