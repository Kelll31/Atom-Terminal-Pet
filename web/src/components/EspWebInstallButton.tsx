import React, { useEffect, useRef, useState } from 'react';
import { PlugZap, Usb } from 'lucide-react';
import { API_BASE } from '../config';

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'esp-web-install-button': any;
    }
  }
}

interface EspWebInstallButtonProps {
  manifestUrl: string;
}

/**
 * Кнопка прошивки через Web Serial.
 *
 * Порт COM держит бэкенд, поэтому перед прошивкой его нужно освободить.
 * Важно: освобождаем только по реальному клику — раньше это происходило
 * даже при наведении мыши, и питомец на минуту терял связь (пропадал звук).
 */
const EspWebInstallButton: React.FC<EspWebInstallButtonProps> = ({ manifestUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [portState, setPortState] = useState<'idle' | 'released' | 'restored'>('idle');

  const releaseSerialPort = async () => {
    try {
      await fetch(`${API_BASE}/api/serial/disconnect`, { method: 'POST' });
      setPortState('released');
    } catch (error) {
      console.warn('Не удалось попросить бэкенд освободить COM-порт:', error);
    }
  };

  const restoreSerialPort = async () => {
    try {
      await fetch(`${API_BASE}/api/serial/connect`, { method: 'POST' });
      setPortState('restored');
    } catch (error) {
      console.warn('Не удалось вернуть COM-порт бэкенду:', error);
    }
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // esp-web-tools сообщает о ходе прошивки событием state-changed
    const onStateChanged = (event: Event) => {
      const state = (event as CustomEvent).detail?.state;
      if (state === 'FINISHED' || state === 'ERROR') {
        setTimeout(restoreSerialPort, 1500);
      }
    };

    container.addEventListener('state-changed', onStateChanged);
    return () => container.removeEventListener('state-changed', onStateChanged);
  }, []);

  return (
    <div ref={containerRef} className="space-y-3">
      <div
        onClick={releaseSerialPort}
        className="flex items-center justify-center rounded-xl border-2 border-cyber-cyan/30 bg-cyber-navy/50 p-6 transition-colors hover:border-cyber-cyan/60"
      >
        {/* @ts-ignore — веб-компонент из esp-web-tools */}
        <esp-web-install-button manifest={manifestUrl}>
          <button slot="unsupported" disabled className="btn-ghost cursor-not-allowed">
            Нужен Chrome или Edge — в этом браузере нет Web Serial
          </button>
          {/* @ts-ignore */}
        </esp-web-install-button>
      </div>

      <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <Usb className="h-3.5 w-3.5" />
          {portState === 'released'
            ? 'COM-порт освобождён для прошивки'
            : portState === 'restored'
              ? 'Связь с питомцем восстановлена'
              : 'Бэкенд держит COM-порт, он освободится по клику'}
        </span>
        <button onClick={restoreSerialPort} className="chip text-slate-300 hover:text-white">
          <PlugZap className="h-3.5 w-3.5" /> Вернуть связь
        </button>
      </div>
    </div>
  );
};

export default EspWebInstallButton;
