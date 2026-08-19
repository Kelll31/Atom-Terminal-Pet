import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from './useAppStore';
import type { Approval, Task } from './useAppStore';

const makeTask = (overrides: Partial<Task> = {}): Task => ({
  id: 't1',
  text: 'Проверь диск',
  title: 'Проверь диск',
  source: 'chat',
  status: 'running',
  steps: [],
  result: '',
  error: '',
  created: Date.now() / 1000,
  finished: null,
  duration: 0,
  ...overrides,
});

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState({
      isConnected: false,
      emotion: 'idle',
      logs: [],
      tasks: [],
      approvals: [],
      chatHistory: [],
      agentStatus: { state: 'idle' },
    });
  });

  it('хранит последние 200 записей журнала', () => {
    for (let i = 0; i < 260; i++) useAppStore.getState().addLog(`Строка ${i}`);

    const { logs } = useAppStore.getState();
    expect(logs).toHaveLength(200);
    expect(logs[logs.length - 1]).toContain('Строка 259');
  });

  it('приводит sleeping к sleepy, чтобы совпадать с прошивкой', () => {
    useAppStore.getState().setEmotion('sleeping');
    expect(useAppStore.getState().emotion).toBe('sleepy');
  });

  it('добавляет сообщение пользователя в историю при постановке задачи', () => {
    useAppStore.getState().sendTask('  проверь git  ');
    const { chatHistory } = useAppStore.getState();
    expect(chatHistory).toHaveLength(1);
    expect(chatHistory[0]).toMatchObject({ sender: 'user', text: 'проверь git' });
  });

  it('игнорирует пустую задачу', () => {
    useAppStore.getState().sendTask('   ');
    expect(useAppStore.getState().chatHistory).toHaveLength(0);
  });

  it('убирает подтверждение из очереди после решения', () => {
    const approval: Approval = {
      id: 'a1',
      task_id: 't1',
      task_title: 'Удалить файл',
      tool: 'delete_path',
      args: { path: 'D:/tmp/x' },
      risk: 'danger',
      description: 'Удаляет файл',
      created: 0,
    };
    useAppStore.setState({ approvals: [approval] });

    useAppStore.getState().resolveApproval('a1', 'allow');
    expect(useAppStore.getState().approvals).toHaveLength(0);
  });

  it('обновляет задачу по идентификатору, а не дублирует её', () => {
    const task = makeTask();
    useAppStore.setState({ tasks: [task] });
    useAppStore.setState({
      tasks: useAppStore.getState().tasks.map(t => (t.id === task.id ? { ...t, status: 'done' } : t)),
    });

    const { tasks } = useAppStore.getState();
    expect(tasks).toHaveLength(1);
    expect(tasks[0].status).toBe('done');
  });
});
