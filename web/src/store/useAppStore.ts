import { create } from 'zustand';
import { WS_BASE } from '../config';

export interface PCMetrics {
  cpu: number;
  ram: number;
  gpu: number;
  temp: number;
  spotify: string;
}

export interface DeviceStatus {
  connected: boolean;
  ip: string;
  ssid: string;
  rssi: number;
  device: string;
  last_seen: string | null;
  transport?: 'none' | 'wifi' | 'usb';
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  isPartial?: boolean;
}

export interface TaskStep {
  id: string;
  type: 'thought' | 'tool_call' | 'tool_result' | 'note';
  ts: number;
  tool: string;
  args: Record<string, unknown>;
  result: string;
  ok: boolean;
  text: string;
  parent: string;
}

export type TaskStatus = 'queued' | 'running' | 'waiting_approval' | 'done' | 'failed' | 'cancelled';

export interface Task {
  id: string;
  text: string;
  title: string;
  source: string;
  status: TaskStatus;
  steps: TaskStep[];
  result: string;
  error: string;
  created: number;
  finished: number | null;
  duration: number;
}

export interface Approval {
  id: string;
  task_id: string;
  task_title: string;
  tool: string;
  args: Record<string, unknown>;
  risk: 'safe' | 'caution' | 'danger';
  description: string;
  created: number;
}

export interface AgentStatus {
  state: 'idle' | 'thinking' | 'working' | 'speaking';
  tool?: string;
  step?: number;
}

interface AppState {
  isConnected: boolean;
  metrics: PCMetrics;
  emotion: string;
  petSays: string;
  deviceStatus: DeviceStatus;
  logs: string[];
  chatHistory: ChatMessage[];
  tasks: Task[];
  approvals: Approval[];
  agentStatus: AgentStatus;

  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  setEmotion: (emotion: string) => void;
  addLog: (log: string) => void;
  sendMessage: (payload: unknown) => void;
  sendBinaryMessage: (payload: ArrayBuffer) => void;

  sendTask: (text: string) => void;
  resolveApproval: (id: string, decision: 'allow' | 'allow_always' | 'deny') => void;
  cancelTask: (taskId: string) => void;
  resetChat: () => void;

  audioListeners: ((data: ArrayBuffer) => void)[];
  addAudioListener: (fn: (data: ArrayBuffer) => void) => void;
  removeAudioListener: (fn: (data: ArrayBuffer) => void) => void;
}

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

/** Бэкенд использует sleeping/sleepy как синонимы — приводим к одному виду. */
const normalizeEmotion = (value: string): string => (value === 'sleeping' ? 'sleepy' : value);

const upsertTask = (tasks: Task[], task: Task): Task[] => {
  const index = tasks.findIndex(t => t.id === task.id);
  if (index === -1) return [task, ...tasks].slice(0, 40);
  const next = [...tasks];
  next[index] = task;
  return next;
};

export const useAppStore = create<AppState>((set, get) => ({
  isConnected: false,
  metrics: { cpu: 0, ram: 0, gpu: 0, temp: 0, spotify: '' },
  emotion: 'idle',
  petSays: '',
  deviceStatus: {
    connected: false,
    ip: 'Оффлайн',
    ssid: '—',
    rssi: 0,
    device: 'M5Stack AtomS3R',
    last_seen: null,
    transport: 'none',
  },
  logs: [],
  chatHistory: [],
  tasks: [],
  approvals: [],
  agentStatus: { state: 'idle' },
  audioListeners: [],

  connectWebSocket: () => {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

    ws = new WebSocket(`${WS_BASE}/ws/pet`);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      set({ isConnected: true });
      get().addLog('Система: соединение с сервером установлено');
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

      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.action) {
        case 'device_status_update':
          set({ deviceStatus: data.device_info });
          break;

        case 'update_pc':
          set({
            metrics: {
              cpu: data.cpu ?? 0,
              ram: data.ram ?? 0,
              gpu: data.gpu ?? 0,
              temp: data.temp ?? 0,
              spotify: data.spotify ?? '',
            },
          });
          break;

        case 'speak':
        case 'set_emotion': {
          if (data.emotion) set({ emotion: normalizeEmotion(data.emotion) });
          if (data.text) {
            set({ petSays: data.text });
            if (data.action === 'speak') {
              set((state) => {
                const history = state.chatHistory.filter(
                  m => !(m.isPartial && m.sender === 'agent'),
                );
                history.push({ id: `${Date.now()}-${history.length}`, sender: 'agent', text: data.text });
                return { chatHistory: history.slice(-60) };
              });
              get().addLog(`Атом: ${data.text}`);
            }
          }
          break;
        }

        case 'agent_status':
          set({ agentStatus: { state: data.state, tool: data.tool, step: data.step } });
          if (data.state === 'thinking') set({ emotion: 'thinking' });
          if (data.state === 'working') set({ emotion: 'working' });
          break;

        case 'tasks_snapshot':
          set({ tasks: data.tasks ?? [] });
          break;

        case 'task_update': {
          const task = data.task as Task;
          set(state => ({ tasks: upsertTask(state.tasks, task) }));
          if (task.status === 'done' || task.status === 'failed' || task.status === 'cancelled') {
            set({ agentStatus: { state: 'idle' } });
          }
          break;
        }

        case 'approval_request':
          set(state => ({ approvals: [...state.approvals.filter(a => a.id !== data.id), data as Approval] }));
          get().addLog(`Подтверждение: ${data.tool}`);
          break;

        case 'approval_resolved':
          set(state => ({ approvals: state.approvals.filter(a => a.id !== data.id) }));
          break;

        case 'user_speech_partial':
          set((state) => {
            const history = [...state.chatHistory];
            const last = history[history.length - 1];
            if (last?.isPartial && last.sender === 'user') {
              history[history.length - 1] = { ...last, text: data.text };
            } else {
              history.push({ id: `${Date.now()}`, sender: 'user', text: data.text, isPartial: true });
            }
            return { chatHistory: history.slice(-60) };
          });
          break;

        case 'user_speech':
          set((state) => {
            const history = [...state.chatHistory];
            const last = history[history.length - 1];
            if (last?.isPartial && last.sender === 'user') {
              history[history.length - 1] = { id: `${Date.now()}`, sender: 'user', text: data.text };
            } else {
              history.push({ id: `${Date.now()}`, sender: 'user', text: data.text });
            }
            return { chatHistory: history.slice(-60) };
          });
          get().addLog(`Вы: ${data.text}`);
          break;

        case 'chat_reset':
          set({ chatHistory: [], tasks: [] });
          break;

        case 'pong':
          break;

        default:
          get().addLog(`Событие: ${JSON.stringify(data).slice(0, 200)}`);
      }
    };

    ws.onclose = () => {
      set({ isConnected: false });
      ws = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => get().connectWebSocket(), 3000);
    };

    ws.onerror = () => {
      ws?.close();
    };
  },

  disconnectWebSocket: () => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    ws?.close();
    ws = null;
  },

  setEmotion: (emotion: string) => set({ emotion: normalizeEmotion(emotion) }),

  addLog: (log: string) =>
    set(state => ({ logs: [...state.logs.slice(-199), `${new Date().toLocaleTimeString()} ${log}`] })),

  sendMessage: (payload: unknown) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    } else {
      console.warn('WebSocket не подключён');
    }
  },

  sendBinaryMessage: (payload: ArrayBuffer) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
  },

  sendTask: (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const message: ChatMessage = { id: `${Date.now()}`, sender: 'user', text: trimmed };
    set(state => ({ chatHistory: [...state.chatHistory, message].slice(-60) }));
    get().sendMessage({ action: 'user_text', text: trimmed, source: 'chat' });
  },

  resolveApproval: (id, decision) => {
    set(state => ({ approvals: state.approvals.filter(a => a.id !== id) }));
    get().sendMessage({ action: 'approve', id, decision });
  },

  cancelTask: (taskId) => get().sendMessage({ action: 'cancel_task', task_id: taskId }),

  resetChat: () => {
    set({ chatHistory: [], tasks: [] });
    get().sendMessage({ action: 'reset_chat' });
  },

  addAudioListener: (fn) => set(state => ({ audioListeners: [...state.audioListeners, fn] })),
  removeAudioListener: (fn) =>
    set(state => ({ audioListeners: state.audioListeners.filter(l => l !== fn) })),
}));
