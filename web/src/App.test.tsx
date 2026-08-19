import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeAll, vi } from 'vitest';
import App from './App';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  // В jsdom нет WebSocket — заглушаем, чтобы стор не падал при монтировании.
  vi.stubGlobal(
    'WebSocket',
    class {
      static OPEN = 1;
      readyState = 0;
      binaryType = '';
      close() {}
      send() {}
    },
  );
});

describe('Оболочка приложения', () => {
  it('показывает навигацию по разделам', () => {
    render(<App />);

    expect(screen.getByText('Панель')).toBeInTheDocument();
    expect(screen.getByText('Инструменты')).toBeInTheDocument();
    expect(screen.getByText('Правила')).toBeInTheDocument();
    expect(screen.getByText('Настройки')).toBeInTheDocument();
    expect(screen.getByText('Прошивка')).toBeInTheDocument();
  });

  it('сообщает об отсутствии связи с сервером', () => {
    render(<App />);
    expect(screen.getByText('нет связи')).toBeInTheDocument();
  });
});
