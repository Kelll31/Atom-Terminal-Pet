import React, { useState, useEffect } from 'react';
import EspWebInstallButton from '../components/EspWebInstallButton';
import { Terminal, Cpu, Zap, Wifi, Server, Key, CheckCircle2, AlertCircle, Usb } from 'lucide-react';
import { API_BASE } from '../config';

const InstallPage: React.FC = () => {
  const [ssid, setSsid] = useState(() => localStorage.getItem('pet_ssid') || '');
  const [password, setPassword] = useState(() => localStorage.getItem('pet_password') || '');
  const [serverIp, setServerIp] = useState(() => localStorage.getItem('pet_serverIp') || '192.168.1.100');
  const [petName, setPetName] = useState(() => localStorage.getItem('pet_petName') || 'Атом');
  
  useEffect(() => { localStorage.setItem('pet_ssid', ssid); }, [ssid]);
  useEffect(() => { localStorage.setItem('pet_password', password); }, [password]);
  useEffect(() => { localStorage.setItem('pet_serverIp', serverIp); }, [serverIp]);
  useEffect(() => { localStorage.setItem('pet_petName', petName); }, [petName]);
  
  // Load settings from backend if available
  useEffect(() => {
    fetch(`${API_BASE}/api/settings`)
      .then(res => res.json())
      .then(data => {
        if (data.pet_name) {
          setPetName(data.pet_name);
        }
      })
      .catch(err => console.error("Could not load backend settings:", err));
  }, []);
  
  const [serialStatus, setSerialStatus] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const manifestUrl = "/firmware/manifest.json";

  const handleConnectAndSend = async (e: React.FormEvent) => {
    e.preventDefault();
    setSerialStatus(null);
    setIsSuccess(false);

    if (!('serial' in navigator)) {
      setSerialStatus('Ошибка: Ваш браузер не поддерживает Web Serial API. Используйте Google Chrome, Microsoft Edge или Opera.');
      return;
    }

    try {
      setIsSending(true);
      setSerialStatus('Запрос на выбор COM-порта...');
      
      // Request serial port
      const selectedPort = await (navigator as any).serial.requestPort();
      await selectedPort.open({ baudRate: 115200 });

      setSerialStatus('Подключено по Serial. Отправка конфигурации...');

      const payload = JSON.stringify({
        ssid: ssid.trim(),
        pass: password.trim(),
        server: serverIp.trim()
      }) + '\n';

      const encoder = new TextEncoder();
      const writer = selectedPort.writable.getWriter();
      await writer.write(encoder.encode(payload));
      writer.releaseLock();

      setSerialStatus('Настройки успешно отправлены на M5Stack! Устройство перезагружается...');
      setIsSuccess(true);

      setTimeout(async () => {
        try {
          await selectedPort.close();
        } catch (_) {}
      }, 2000);

    } catch (err: any) {
      console.error('Serial Error:', err);
      if (err.name === 'NotFoundError') {
        setSerialStatus('Выбор порта отменен.');
      } else {
        setSerialStatus(`Ошибка Serial: ${err.message || err}`);
      }
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 space-y-8 max-w-4xl mx-auto">
      
      {/* Header text */}
      <div className="text-center space-y-4 max-w-2xl">
        <div className="inline-flex items-center justify-center p-4 bg-cyber-cyan/10 rounded-full mb-2 ring-1 ring-cyber-cyan/30">
          <Cpu className="w-10 h-10 text-cyber-cyan" />
        </div>
        <h2 className="text-4xl font-bold text-white tracking-tight">
          Установка и Настройка
        </h2>
        <p className="text-gray-400 text-base">
          Прошивка Atom-Terminal-Pet и настройка параметров Wi-Fi / Сервера в один клик.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full">
        
        {/* Step 1: Web Flasher */}
        <div className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-2xl shadow-xl space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-cyber-dark rounded-lg ring-1 ring-gray-800">
              <Terminal className="w-5 h-5 text-cyber-emerald" />
            </div>
            <div>
              <span className="text-xs text-cyber-emerald uppercase font-bold tracking-wider">Шаг 1</span>
              <h3 className="text-lg font-semibold">Прошивка через Web Serial</h3>
            </div>
          </div>

          <p className="text-sm text-gray-400">
            Подключите M5Stack по USB. Нажмите кнопку прошивки и выберите порт.
          </p>

          <EspWebInstallButton manifestUrl={manifestUrl} />
        </div>

        {/* Step 2: Wi-Fi (Improv / Web Serial) Config */}
        <div className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-2xl shadow-xl space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-cyber-dark rounded-lg ring-1 ring-gray-800">
              <Wifi className="w-5 h-5 text-cyber-cyan" />
            </div>
            <div>
              <span className="text-xs text-cyber-cyan uppercase font-bold tracking-wider">Шаг 2</span>
              <h3 className="text-lg font-semibold">Настройка Wi-Fi и Сервера</h3>
            </div>
          </div>

          <form onSubmit={handleConnectAndSend} className="space-y-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
                <Wifi className="w-3.5 h-3.5 text-cyber-cyan" /> Имя сети Wi-Fi (SSID)
              </label>
              <input
                type="text"
                required
                value={ssid}
                onChange={(e) => setSsid(e.target.value)}
                placeholder="Имя вашей Wi-Fi сети"
                className="w-full bg-cyber-dark border border-gray-800 rounded px-3 py-2 text-sm text-white focus:border-cyber-cyan outline-none transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
                <Key className="w-3.5 h-3.5 text-yellow-500" /> Пароль от Wi-Fi
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Пароль Wi-Fi"
                className="w-full bg-cyber-dark border border-gray-800 rounded px-3 py-2 text-sm text-white focus:border-cyber-cyan outline-none transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
                <Server className="w-3.5 h-3.5 text-purple-400" /> IP-адрес ПК с Бэкендом
              </label>
              <input
                type="text"
                required
                value={serverIp}
                onChange={(e) => setServerIp(e.target.value)}
                placeholder="Например: 192.168.1.100"
                className="w-full bg-cyber-dark border border-gray-800 rounded px-3 py-2 text-sm text-white focus:border-cyber-cyan outline-none transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
                <Terminal className="w-3.5 h-3.5 text-pink-400" /> Кличка питомца
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  required
                  value={petName}
                  onChange={(e) => setPetName(e.target.value)}
                  placeholder="Например: Атом"
                  className="flex-1 bg-cyber-dark border border-gray-800 rounded px-3 py-2 text-sm text-white focus:border-cyber-cyan outline-none transition-colors"
                />
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const res = await fetch(`${API_BASE}/api/settings`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ pet_name: petName })
                      });
                      if (res.ok) {
                        setSerialStatus('Кличка успешно сохранена на сервере!');
                        setIsSuccess(true);
                      }
                    } catch (e) {
                      setSerialStatus('Ошибка сохранения на сервере.');
                    }
                  }}
                  className="px-4 py-2 bg-pink-500/20 border border-pink-500 text-pink-500 hover:bg-pink-500/30 rounded font-semibold text-sm transition-colors"
                >
                  Сохранить
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSending || !ssid.trim()}
              className="w-full py-2.5 px-4 bg-cyber-cyan/20 border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan/30 rounded font-semibold text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Usb className="w-4 h-4" />
              {isSending ? 'Передача данных...' : 'Передать настройки Wi-Fi по USB'}
            </button>
          </form>

          {serialStatus && (
            <div className={`p-3 rounded border text-xs flex items-start gap-2 ${
              isSuccess 
                ? 'bg-cyber-emerald/10 border-cyber-emerald/40 text-cyber-emerald' 
                : 'bg-cyber-dark border-gray-700 text-gray-300'
            }`}>
              {isSuccess ? <CheckCircle2 className="w-4 h-4 text-cyber-emerald shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 text-cyber-cyan shrink-0 mt-0.5" />}
              <span>{serialStatus}</span>
            </div>
          )}
        </div>

      </div>

      {/* Footer Info */}
      <div className="text-center text-xs text-gray-500 max-w-md pt-4">
        <p className="flex items-center justify-center gap-1">
          <Zap className="w-3.5 h-3.5 text-yellow-500" />
          Web Serial API • Автоматическое сохранение параметров в NVS Flash
        </p>
      </div>

    </div>
  );
};

export default InstallPage;
