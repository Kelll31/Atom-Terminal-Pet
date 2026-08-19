import React, { useState, useEffect } from 'react';
import { Settings2, Plus, Trash2, Save, Activity, Zap } from 'lucide-react';

interface Rule {
  id: string;
  description: string;
  condition: {
    metric: string;
    operator: string;
    value: number;
    duration_seconds: number;
  };
  action: {
    type: string;
    emotion: string;
    text: string;
  };
}

const RulesPage: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    fetchRules();
  }, []);

  const fetchRules = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/rules');
      const data = await res.json();
      setRules(data.rules || []);
    } catch (e) {
      console.error("Failed to fetch rules", e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await fetch('http://localhost:8000/api/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules })
      });
      alert('Rules saved and applied successfully!');
    } catch (e) {
      console.error("Failed to save rules", e);
      alert('Failed to save rules.');
    } finally {
      setIsSaving(false);
    }
  };

  const addRule = () => {
    const newRule: Rule = {
      id: `rule_${Date.now()}`,
      description: "New Rule",
      condition: { metric: "cpu", operator: ">", value: 80, duration_seconds: 5 },
      action: { type: "set_emotion", emotion: "angry", text: "Too much CPU!" }
    };
    setRules([...rules, newRule]);
  };

  const removeRule = (id: string) => {
    setRules(rules.filter(r => r.id !== id));
  };

  const updateRule = (id: string, field: string, value: any) => {
    setRules(rules.map(r => {
      if (r.id !== id) return r;
      const parts = field.split('.');
      if (parts.length === 1) {
        return { ...r, [field]: value };
      } else {
        return {
          ...r,
          [parts[0]]: {
            ...(r as any)[parts[0]],
            [parts[1]]: value
          }
        };
      }
    }));
  };

  if (isLoading) return <div className="p-8 text-center text-cyber-cyan">Loading rules...</div>;

  return (
    <div className="flex-1 p-8 max-w-5xl mx-auto w-full animate-fade-in space-y-8">
      
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold flex items-center gap-2">
            <Settings2 className="w-8 h-8 text-cyber-cyan" />
            Rule Configurator
          </h2>
          <p className="text-gray-400 mt-2">Visually edit triggers and reactions.</p>
        </div>
        <button 
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-6 py-3 bg-cyber-emerald/20 text-cyber-emerald border border-cyber-emerald rounded-lg hover:bg-cyber-emerald/30 transition-colors"
        >
          <Save className="w-5 h-5" />
          {isSaving ? 'Saving...' : 'Save & Deploy'}
        </button>
      </div>

      <div className="space-y-6">
        {rules.map((rule) => (
          <div key={rule.id} className="bg-cyber-navy/40 border border-cyber-navy p-6 rounded-xl relative group">
            
            <button 
              onClick={() => removeRule(rule.id)}
              className="absolute top-4 right-4 p-2 text-gray-500 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <Trash2 className="w-5 h-5" />
            </button>

            <div className="mb-4">
              <input 
                type="text" 
                value={rule.description}
                onChange={(e) => updateRule(rule.id, 'description', e.target.value)}
                className="bg-transparent text-xl font-bold text-white border-b border-transparent hover:border-cyber-cyan focus:border-cyber-cyan outline-none transition-colors w-2/3"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 bg-cyber-dark/50 p-4 rounded-lg border border-gray-800">
              
              {/* IF Condition */}
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-cyber-cyan uppercase tracking-wider flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  IF (Condition)
                </h3>
                
                <div className="flex items-center gap-3">
                  <select 
                    value={rule.condition.metric}
                    onChange={(e) => updateRule(rule.id, 'condition.metric', e.target.value)}
                    className="bg-cyber-navy border border-gray-700 text-white rounded p-2 outline-none focus:border-cyber-cyan"
                  >
                    <option value="cpu">CPU Usage (%)</option>
                    <option value="ram">RAM Usage (%)</option>
                    <option value="temp">CPU Temp (°C)</option>
                  </select>

                  <select 
                    value={rule.condition.operator}
                    onChange={(e) => updateRule(rule.id, 'condition.operator', e.target.value)}
                    className="bg-cyber-navy border border-gray-700 text-white rounded p-2 outline-none focus:border-cyber-cyan"
                  >
                    <option value=">">&gt;</option>
                    <option value="<">&lt;</option>
                    <option value="==">==</option>
                  </select>

                  <input 
                    type="number" 
                    value={rule.condition.value}
                    onChange={(e) => updateRule(rule.id, 'condition.value', Number(e.target.value))}
                    className="bg-cyber-navy border border-gray-700 text-white rounded p-2 w-20 outline-none focus:border-cyber-cyan"
                  />
                </div>
                
                <div className="flex items-center gap-3 text-sm text-gray-400">
                  <span>Sustained for</span>
                  <input 
                    type="number" 
                    value={rule.condition.duration_seconds}
                    onChange={(e) => updateRule(rule.id, 'condition.duration_seconds', Number(e.target.value))}
                    className="bg-cyber-navy border border-gray-700 text-white rounded p-1 w-16 text-center outline-none focus:border-cyber-cyan"
                  />
                  <span>seconds</span>
                </div>
              </div>

              {/* THEN Action */}
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-cyber-emerald uppercase tracking-wider flex items-center gap-2">
                  <Zap className="w-4 h-4" />
                  THEN (Action)
                </h3>

                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400">Set Emotion:</span>
                    <select 
                      value={rule.action.emotion}
                      onChange={(e) => updateRule(rule.id, 'action.emotion', e.target.value)}
                      className="bg-cyber-navy border border-gray-700 text-white rounded p-2 outline-none focus:border-cyber-cyan"
                    >
                      <option value="idle">Idle</option>
                      <option value="happy">Happy</option>
                      <option value="angry">Angry</option>
                      <option value="sleepy">Sleepy</option>
                      <option value="panic">Panic</option>
                    </select>
                  </div>
                  
                  <div className="flex flex-col gap-1">
                    <span className="text-gray-400 text-sm">Speech Text:</span>
                    <input 
                      type="text" 
                      value={rule.action.text}
                      onChange={(e) => updateRule(rule.id, 'action.text', e.target.value)}
                      placeholder="Optional text to speak..."
                      className="bg-cyber-navy border border-gray-700 text-white rounded p-2 outline-none focus:border-cyber-cyan w-full"
                    />
                  </div>
                </div>
              </div>

            </div>
          </div>
        ))}
      </div>

      <button 
        onClick={addRule}
        className="w-full p-4 border-2 border-dashed border-gray-700 hover:border-cyber-cyan text-gray-400 hover:text-cyber-cyan rounded-xl flex items-center justify-center gap-2 transition-colors"
      >
        <Plus className="w-5 h-5" />
        Add New Rule
      </button>

    </div>
  );
};

export default RulesPage;
