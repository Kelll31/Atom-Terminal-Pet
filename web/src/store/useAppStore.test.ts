import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from './useAppStore';

describe('useAppStore', () => {
  beforeEach(() => {
    // Reset store state
    useAppStore.setState({
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
    });
  });

  it('adds log messages and limits to 50', () => {
    const store = useAppStore.getState();
    expect(store.logs).toHaveLength(0);

    // Add 60 logs
    for (let i = 0; i < 60; i++) {
      useAppStore.getState().addLog(`Log ${i}`);
    }

    const updatedStore = useAppStore.getState();
    expect(updatedStore.logs).toHaveLength(50);
    expect(updatedStore.logs[0]).toBe('Log 10');
    expect(updatedStore.logs[49]).toBe('Log 59');
  });

  it('sets emotion', () => {
    const store = useAppStore.getState();
    expect(store.emotion).toBe('idle');

    store.setEmotion('happy');
    expect(useAppStore.getState().emotion).toBe('happy');
  });
});
