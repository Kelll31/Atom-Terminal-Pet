import React, { useEffect, useRef } from 'react';

// Declare the custom element so TypeScript doesn't complain
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'esp-web-install-button': any;
    }
  }
}

interface EspWebInstallButtonProps {
  manifestUrl: string;
}

const EspWebInstallButton: React.FC<EspWebInstallButtonProps> = ({ manifestUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const releaseSerialPort = async () => {
    try {
      await fetch('http://localhost:8000/api/serial/disconnect', { method: 'POST' });
    } catch (e) {
      console.warn('Could not notify backend to release serial port:', e);
    }
  };

  useEffect(() => {
    // Add event listeners to automatically release serial port before flashing
    const container = containerRef.current;
    if (container) {
      container.addEventListener('pointerdown', releaseSerialPort);
    }
    return () => {
      if (container) {
        container.removeEventListener('pointerdown', releaseSerialPort);
      }
    };
  }, []);

  return (
    <div 
      ref={containerRef} 
      onClick={releaseSerialPort}
      onMouseEnter={releaseSerialPort}
      className="flex justify-center items-center p-6 border-2 border-cyber-cyan/30 rounded-xl bg-cyber-navy/50 hover:border-cyber-cyan/60 transition-colors shadow-[0_0_15px_rgba(0,240,255,0.1)]"
    >
      {/* The install button reads the manifest attribute */}
      {/* @ts-ignore */}
      <esp-web-install-button manifest={manifestUrl}>
        {/* Custom fallback content if Web Serial is not supported */}
        <button slot="unsupported" disabled className="px-6 py-3 bg-gray-600 text-gray-300 rounded cursor-not-allowed">
          Браузер не поддерживает Web Serial (Используйте Chrome/Edge)
        </button>
      {/* @ts-ignore */}
      </esp-web-install-button>
    </div>
  );
};

export default EspWebInstallButton;
