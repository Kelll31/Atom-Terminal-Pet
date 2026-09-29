import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from './SettingsPage';

const SETTINGS = {
  api_key: '',
  api_key_set: false,
  base_url: '',
  model_name: 'gpt-4o-mini',
  temperature: 0.4,
  max_steps: 12,
  pet_name: 'Патрик',
  wake_words: ['патрик'],
  require_wake_word: true,
  speak_replies: true,
  audio_output: 'both',
  autonomy: 'auto_safe',
  allowed_roots: [],
  mcp_enabled: true,
  voice_enabled: true,
  live_mode: true,
  conversation_window_sec: 45,
  vad_sensitivity: 2.6,
  vad_min_level: 0.012,
  endpoint_silence_sec: 0.8,
  barge_in: true,
  stt_engine: 'vosk',
  stt_model: 'whisper-1',
  stt_base_url: '',
  stt_api_key: '',
  stt_api_key_set: false,
  auto_check_updates: true,
  update_url: '',
  panel_window: true,
};

const UPDATE_STATE = {
  current: '1.0.0',
  available: null,
  last_check: 0,
  last_error: '',
  downloading: false,
  progress: 0,
  installable: false,
  from_sources: false,
};

const LOCAL_SERVER = {
  name: 'LM Studio / Bionic',
  base_url: 'http://127.0.0.1:1234/v1',
  models: [
    { id: 'qwen3-8b', type: 'llm', state: 'loaded', context: 32768 },
    { id: 'gemma-3-4b', type: 'llm', state: 'not-loaded', context: 8192 },
  ],
};

/** Отвечает на запросы страницы: настройки, поиск сервера, список моделей. */
const mockFetch = (discover: { servers: unknown[] }) =>
  vi.fn(async (url: string) => {
    if (url.endsWith('/api/settings')) return { json: async () => SETTINGS } as Response;
    if (url.endsWith('/api/update')) return { json: async () => UPDATE_STATE } as Response;
    if (url.endsWith('/api/llm/discover')) {
      return { json: async () => ({ status: 'success', ...discover }) } as Response;
    }
    if (url.endsWith('/api/llm/models')) {
      return {
        json: async () => ({ status: 'success', models: LOCAL_SERVER.models, skipped_embeddings: 0 }),
      } as Response;
    }
    throw new Error(`Неожиданный запрос: ${url}`);
  });

describe('Настройки: подключение локальной модели', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('находит запущенный локальный сервер и подставляет его модель', async () => {
    vi.stubGlobal('fetch', mockFetch({ servers: [LOCAL_SERVER] }));
    const user = userEvent.setup();
    render(<SettingsPage />);

    await screen.findByPlaceholderText('Пусто — официальный OpenAI');
    await user.click(screen.getByRole('button', { name: /Найти локальную модель/ }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Пусто — официальный OpenAI')).toHaveValue('http://127.0.0.1:1234/v1');
    });
    // Из двух моделей выбирается уже загруженная в память
    expect(screen.getByLabelText('Модель')).toHaveValue('qwen3-8b');
    expect(screen.getByLabelText('Модели сервера')).toBeInTheDocument();
    expect(screen.getByText(/Локальный сервер: ключ не нужен/)).toBeInTheDocument();
  });

  it('подсказывает запустить сервер, если ничего не нашлось', async () => {
    vi.stubGlobal('fetch', mockFetch({ servers: [] }));
    const user = userEvent.setup();
    render(<SettingsPage />);

    await screen.findByPlaceholderText('Пусто — официальный OpenAI');
    await user.click(screen.getByRole('button', { name: /Найти локальную модель/ }));

    expect(await screen.findByText(/Локальный сервер не найден/)).toBeInTheDocument();
  });

  it('пресет LM Studio подтягивает список моделей сервера', async () => {
    vi.stubGlobal('fetch', mockFetch({ servers: [] }));
    const user = userEvent.setup();
    render(<SettingsPage />);

    await screen.findByPlaceholderText('Пусто — официальный OpenAI');
    await user.click(screen.getByRole('button', { name: 'LM Studio / Bionic' }));

    await waitFor(() => expect(screen.getByLabelText('Модель')).toHaveValue('qwen3-8b'));
    expect(screen.getByPlaceholderText('Локальной модели ключ не требуется')).toBeInTheDocument();
  });
});
