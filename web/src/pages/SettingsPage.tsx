import React, { useState, useEffect } from 'react';
import { Save, Play, CheckCircle, AlertTriangle } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [modelName, setModelName] = useState('');
  
  const [status, setStatus] = useState<{type: 'idle' | 'loading' | 'success' | 'error', msg: string}>({ type: 'idle', msg: '' });

  useEffect(() => {
    // Load settings from backend
    fetch('http://localhost:8000/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data) {
          setApiKey(data.api_key || '');
          setBaseUrl(data.base_url || '');
          setModelName(data.model_name || '');
        }
      })
      .catch(err => console.error("Failed to load settings:", err));
  }, []);

  const handleSave = async () => {
    setStatus({ type: 'loading', msg: 'Saving...' });
    try {
      const res = await fetch('http://localhost:8000/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model_name: modelName })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setStatus({ type: 'success', msg: 'Settings saved successfully!' });
      } else {
        setStatus({ type: 'error', msg: 'Failed to save settings.' });
      }
    } catch (e: any) {
      setStatus({ type: 'error', msg: e.message });
    }
  };

  const handleTest = async () => {
    setStatus({ type: 'loading', msg: 'Testing connection (this may take a few seconds)...' });
    try {
      const res = await fetch('http://localhost:8000/api/settings/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model_name: modelName })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setStatus({ type: 'success', msg: `Connection successful! LLM replied: "${data.message}"` });
      } else {
        setStatus({ type: 'error', msg: `Test failed: ${data.message}` });
      }
    } catch (e: any) {
      setStatus({ type: 'error', msg: `Network Error: ${e.message}` });
    }
  };

  return (
    <div className="flex-1 p-8 max-w-3xl mx-auto w-full space-y-8 animate-fade-in">
      <div>
        <h2 className="text-3xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">AI Settings</h2>
        <p className="text-gray-400">Configure your connection to OpenRouter, OpenAI, or local LLMs.</p>
      </div>

      <div className="bg-cyber-navy/40 border border-cyber-navy rounded-xl p-6 space-y-6">
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300 uppercase tracking-widest">Provider Presets</label>
          <select 
            className="w-full bg-cyber-dark border border-cyber-navy rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyber-cyan transition-colors"
            onChange={(e) => {
              const val = e.target.value;
              if (val === 'openrouter') {
                setBaseUrl('https://openrouter.ai/api/v1');
                setModelName('google/gemini-2.5-flash');
              } else if (val === 'ollama') {
                setBaseUrl('http://localhost:11434/v1');
                setModelName('llama3');
              } else if (val === 'deepseek') {
                setBaseUrl('https://api.deepseek.com/v1');
                setModelName('deepseek-chat');
              } else if (val === 'openai') {
                setBaseUrl('');
                setModelName('gpt-4o');
              }
            }}
          >
            <option value="custom">-- Select a Preset (Optional) --</option>
            <option value="openrouter">OpenRouter (Gemini / Claude / etc)</option>
            <option value="ollama">Local Ollama (llama3 / phi)</option>
            <option value="deepseek">DeepSeek API</option>
            <option value="openai">OpenAI (Default)</option>
          </select>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300 uppercase tracking-widest">Base URL</label>
          <input 
            type="text" 
            placeholder="e.g. https://openrouter.ai/api/v1 (Leave blank for default OpenAI)" 
            className="w-full bg-cyber-dark border border-cyber-navy rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyber-cyan transition-colors"
            value={baseUrl}
            onChange={e => setBaseUrl(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300 uppercase tracking-widest">API Key</label>
          <input 
            type="password" 
            placeholder="sk-or-v1-..." 
            className="w-full bg-cyber-dark border border-cyber-navy rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyber-cyan transition-colors"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300 uppercase tracking-widest">Model Name</label>
          <input 
            type="text" 
            placeholder="e.g. google/gemini-2.5-flash" 
            className="w-full bg-cyber-dark border border-cyber-navy rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyber-cyan transition-colors"
            value={modelName}
            onChange={e => setModelName(e.target.value)}
          />
        </div>

        {status.type !== 'idle' && (
          <div className={`p-4 rounded-lg flex items-start gap-3 border ${
            status.type === 'error' ? 'bg-red-500/10 border-red-500/50 text-red-400' :
            status.type === 'success' ? 'bg-cyber-emerald/10 border-cyber-emerald/50 text-cyber-emerald' :
            'bg-cyber-cyan/10 border-cyber-cyan/50 text-cyber-cyan'
          }`}>
            {status.type === 'error' && <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />}
            {status.type === 'success' && <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />}
            {status.type === 'loading' && <div className="w-5 h-5 border-2 border-cyber-cyan border-t-transparent rounded-full animate-spin flex-shrink-0 mt-0.5" />}
            <span className="text-sm break-all">{status.msg}</span>
          </div>
        )}

        <div className="flex items-center gap-4 pt-4">
          <button 
            onClick={handleSave}
            disabled={status.type === 'loading'}
            className="flex-1 bg-cyber-cyan hover:bg-cyber-cyan/80 text-black font-bold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Save className="w-5 h-5" /> Save Settings
          </button>
          
          <button 
            onClick={handleTest}
            disabled={status.type === 'loading' || !apiKey}
            className="flex-1 bg-cyber-navy hover:bg-cyber-navy/80 border border-cyber-cyan/30 text-white font-bold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Play className="w-5 h-5 text-cyber-cyan" /> Test Connection
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
