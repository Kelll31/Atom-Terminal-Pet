import { create } from 'zustand';

interface PCMetrics {
  cpu: number;
  ram: number;
  gpu: number;
  temp: number;
  spotify: string;
}

interface DeviceStatus {
  connected: boolean;
  ip: string;
  ssid: string;
  rssi: number;
  device: string;
  last_seen: string | null;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  isPartial?: boolean;
}

interface AppState {
  isConnected: boolean;
  metrics: PCMetrics;
  emotion: string;
  deviceStatus: DeviceStatus;
  logs: string[];
  chatHistory: ChatMessage[];
  
  // Actions
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  setEmotion: (emotion: string) => void;
  addLog: (log: string) => void;
  sendMessage: (payload: any) => void;
  sendBinaryMessage: (payload: ArrayBuffer) => void;
  audioListeners: ((data: ArrayBuffer) => void)[];
  addAudioListener: (fn: (data: ArrayBuffer) => void) => void;
  removeAudioListener: (fn: (data: ArrayBuffer) => void) => void;
}

let ws: WebSocket | null = null;

export const useAppStore = create<AppState>((set, get) => ({
  isConnected: false,
  metrics: { cpu: 0, ram: 0, gpu: 0, temp: 0, spotify: 'Nothing' },
  emotion: 'idle',
  deviceStatus: {
    connected: false,
    ip: 'Offline',
    ssid: 'Disconnected',
    rssi: 0,
    device: 'M5Stack AtomS3',
    last_seen: null,
  },
  logs: [],
  chatHistory: [],
  audioListeners: [],

  connectWebSocket: () => {
    if (ws) return; // Already connected or connecting

    const wsUrl = `ws://${window.location.hostname || 'localhost'}:8000/ws/pet`;
    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      set({ isConnected: true });
      get().addLog('System: WebSocket Connected');
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        get().audioListeners.forEach(fn => fn(event.data));
        return;
      }
      if (event.data instanceof Blob) {
        const buffer = await event.data.arrayBuffer();
        get().audioListeners.forEach(fn => fn(buffer));
        return;
      }
      try {
        const data = JSON.parse(event.data);
        
        if (data.action === 'device_status_update' && data.device_info) {
          set({ deviceStatus: data.device_info });
          get().addLog(`System: Device status update [IP: ${data.device_info.ip}, SSID: ${data.device_info.ssid}]`);
        } else if (data.action === 'update_pc') {
          set({
            metrics: {
              cpu: data.cpu ?? 0,
              ram: data.ram ?? 0,
              gpu: data.gpu ?? 0,
              temp: data.temp ?? 0,
              spotify: data.spotify ?? 'Nothing'
            }
          });
        } else if (data.action === 'speak' || data.action === 'set_emotion') {
          if (data.emotion) {
            set({ emotion: data.emotion });
          }
          if (data.text) {
            set((state) => {
              const history = [...state.chatHistory];
              // Remove thinking placeholder
              if (history.length > 0 && history[history.length - 1].isPartial && history[history.length - 1].sender === 'agent') {
                history.pop();
              }
              history.push({ id: Date.now().toString(), sender: 'agent', text: data.text });
              return { chatHistory: history.slice(-50) };
            });
          }
          get().addLog(`Agent: ${data.text || ''} [Emotion: ${data.emotion}]`);
        } else if (data.action === 'user_speech_partial') {
          set((state) => {
            const history = [...state.chatHistory];
            if (history.length > 0 && history[history.length - 1].isPartial && history[history.length - 1].sender === 'user') {
              history[history.length - 1].text = data.text;
            } else {
              history.push({ id: Date.now().toString(), sender: 'user', text: data.text, isPartial: true });
            }
            return { chatHistory: history.slice(-50) };
          });
        } else if (data.action === 'user_speech') {
          set((state) => {
            const history = [...state.chatHistory];
            if (history.length > 0 && history[history.length - 1].isPartial && history[history.length - 1].sender === 'user') {
              history[history.length - 1] = { id: Date.now().toString(), sender: 'user', text: data.text };
            } else {
              history.push({ id: Date.now().toString(), sender: 'user', text: data.text });
            }
            return { chatHistory: history.slice(-50) };
          });
          get().addLog(`User: ${data.text}`);
        } else if (data.action === 'agent_thinking') {
          set((state) => {
            const history = [...state.chatHistory];
            history.push({ id: Date.now().toString(), sender: 'agent', text: '...', isPartial: true });
            return { chatHistory: history.slice(-50) };
          });
        } else {
          get().addLog(`Received: ${JSON.stringify(data)}`);
        }
      } catch (e) {
        // Might be binary audio data, ignore for UI store
      }
    };

    ws.onclose = () => {
      set({ isConnected: false });
      ws = null;
      get().addLog('System: WebSocket Disconnected. Reconnecting in 3s...');
      setTimeout(() => {
        get().connectWebSocket();
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      ws?.close();
    };
  },

  disconnectWebSocket: () => {
    if (ws) {
      ws.close();
      ws = null;
    }
  },

  setEmotion: (emotion: string) => set({ emotion }),

  addLog: (log: string) => set((state) => ({ 
    logs: [...state.logs.slice(-49), log] // Keep last 50 logs
  })),

  sendMessage: (payload: any) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    } else {
      console.warn("Cannot send message, WebSocket not connected");
    }
  },

  sendBinaryMessage: (payload: ArrayBuffer) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
    } else {
      console.warn("Cannot send binary message, WebSocket not connected");
    }
  },

  addAudioListener: (fn) => set((state) => ({
    audioListeners: [...state.audioListeners, fn]
  })),

  removeAudioListener: (fn) => set((state) => ({
    audioListeners: state.audioListeners.filter(l => l !== fn)
  }))
}));
