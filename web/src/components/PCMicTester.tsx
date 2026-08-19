import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

export const PCMicTester: React.FC = () => {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [isRecording, setIsRecording] = useState(false);
  const sendBinaryMessage = useAppStore(state => state.sendBinaryMessage);
  const isConnected = useAppStore(state => state.isConnected);

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  useEffect(() => {
    const getDevices = async () => {
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        const devs = await navigator.mediaDevices.enumerateDevices();
        const audioDevs = devs.filter(d => d.kind === 'audioinput');
        setDevices(audioDevs);
        if (audioDevs.length > 0) {
          setSelectedDeviceId(audioDevs[0].deviceId);
        }
      } catch (err) {
        console.error("Failed to enumerate devices", err);
      }
    };
    getDevices();
  }, []);

  const startRecording = async () => {
    if (!isConnected) {
      console.warn("Backend not connected");
      return;
    }
    
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: selectedDeviceId ? { exact: selectedDeviceId } : undefined }
      });
      streamRef.current = stream;

      // Force 16000Hz sampling rate
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
      const context = new AudioContext({ sampleRate: 16000 });
      contextRef.current = context;

      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      source.connect(processor);
      processor.connect(context.destination);

      processor.onaudioprocess = (e) => {
        const float32Data = e.inputBuffer.getChannelData(0);
        
        // Convert Float32 to Int16 PCM
        const pcmData = new Int16Array(float32Data.length);
        for (let i = 0; i < float32Data.length; i++) {
          let s = Math.max(-1, Math.min(1, float32Data[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Send binary frame
        sendBinaryMessage(pcmData.buffer);
      };

      setIsRecording(true);
    } catch (err) {
      console.error("Failed to start recording", err);
    }
  };

  const stopRecording = () => {
    if (processorRef.current && contextRef.current) {
      processorRef.current.disconnect();
      contextRef.current.close();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
    }
    
    setIsRecording(false);
  };

  return (
    <div className="flex items-center gap-2 bg-cyber-navy/50 px-4 py-2 rounded-full border border-cyber-navy">
      <select
        className="bg-transparent text-sm text-gray-300 outline-none max-w-[150px] truncate"
        value={selectedDeviceId}
        onChange={(e) => setSelectedDeviceId(e.target.value)}
        disabled={isRecording}
      >
        {devices.map(d => (
          <option key={d.deviceId} value={d.deviceId} className="bg-cyber-dark">
            {d.label || `Microphone ${d.deviceId.slice(0,5)}...`}
          </option>
        ))}
      </select>

      <button
        onClick={isRecording ? stopRecording : startRecording}
        disabled={!isConnected}
        className={`flex items-center justify-center p-1.5 rounded-full transition-colors ${
          isRecording 
            ? 'bg-red-500/20 text-red-500 hover:bg-red-500/30 animate-pulse' 
            : 'bg-cyber-cyan/10 text-cyber-cyan hover:bg-cyber-cyan/20'
        } ${!isConnected ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={isRecording ? "Stop PC Mic" : "Start PC Mic"}
      >
        {isRecording ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
      </button>
    </div>
  );
};
