import React, { useState, useEffect, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import { Mic, MicOff } from 'lucide-react';

export const MicStreamPlayer: React.FC = () => {
  const [isListening, setIsListening] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const nextStartTimeRef = useRef<number>(0);
  
  const addAudioListener = useAppStore(state => state.addAudioListener);
  const removeAudioListener = useAppStore(state => state.removeAudioListener);
  const isConnected = useAppStore(state => state.isConnected);

  useEffect(() => {
    const handleAudioData = (buffer: ArrayBuffer) => {
      if (!isListening || !audioCtxRef.current) return;
      
      const ctx = audioCtxRef.current;
      const int16 = new Int16Array(buffer);
      console.log(`[MicStream] Received ${int16.length} audio samples`);
      
      if (int16.length === 0) return;
      const float32 = new Float32Array(int16.length);
      
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
      }
      
      const audioBuffer = ctx.createBuffer(1, float32.length, 16000);
      audioBuffer.getChannelData(0).set(float32);
      
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      
      const currentTime = ctx.currentTime;
      if (nextStartTimeRef.current < currentTime) {
        nextStartTimeRef.current = currentTime + 0.05;
      }
      
      source.start(nextStartTimeRef.current);
      nextStartTimeRef.current += audioBuffer.duration;
    };

    if (isListening) {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new window.AudioContext();
      }
      if (audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume();
      }
      nextStartTimeRef.current = audioCtxRef.current.currentTime + 0.1;
      addAudioListener(handleAudioData);
    } else {
      if (audioCtxRef.current && audioCtxRef.current.state === 'running') {
        audioCtxRef.current.suspend();
      }
      removeAudioListener(handleAudioData);
    }

    return () => {
      removeAudioListener(handleAudioData);
    };
  }, [isListening, addAudioListener, removeAudioListener]);

  useEffect(() => {
    if (!isConnected && isListening) {
      setIsListening(false);
    }
  }, [isConnected, isListening]);

  return (
    <button
      onClick={() => setIsListening(!isListening)}
      disabled={!isConnected}
      className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-colors ${
        !isConnected 
          ? 'bg-gray-800/50 text-gray-500 border-gray-700 cursor-not-allowed'
          : isListening 
            ? 'bg-red-900/40 text-red-400 border-red-700 animate-pulse' 
            : 'bg-cyber-navy/50 text-cyber-cyan border-cyber-navy hover:bg-cyber-navy/80'
      }`}
      title={isListening ? 'Stop listening to Atom Mic' : 'Listen to Atom Mic'}
    >
      {isListening ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
      <span className="text-sm font-medium">
        {isListening ? 'Live Mic' : 'Listen Mic'}
      </span>
    </button>
  );
};
