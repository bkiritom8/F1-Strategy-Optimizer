import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, User, Bot, Loader2, Info, Sparkles } from 'lucide-react';
import { RaceSimulator } from '../components/simulation';
import { apiFetch } from '../services/client';
import type { ChatResponse } from '../services/endpoints';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const BACKEND_MODEL_LABEL = 'gemini-2.5-flash (backend)';

/** Keywords that suggest the user wants a race simulation. */
const SIMULATION_KEYWORDS = [
  'simulate', 'simulation', 'monte carlo', 'race result', 'race outcome',
  'predict race', 'who will win', 'finish position', 'lap by lap', 'replay',
];

/**
 * Returns true when the question likely requests a simulation.
 * Matches case-insensitively against SIMULATION_KEYWORDS.
 */
function isSimulationQuestion(question: string): boolean {
  const lower = question.toLowerCase();
  return SIMULATION_KEYWORDS.some((kw) => lower.includes(kw));
}

/**
 * Extracts a race/circuit ID from the question text.
 * Falls back to 'monaco' when no known circuit is mentioned.
 */
function extractRaceId(question: string): string {
  const lower = question.toLowerCase();
  const CIRCUIT_MAP: Record<string, string> = {
    bahrain: 'bahrain',
    jeddah: 'jeddah',
    saudi: 'jeddah',
    melbourne: 'melbourne',
    australia: 'melbourne',
    suzuka: 'suzuka',
    japan: 'suzuka',
    shanghai: 'shanghai',
    china: 'shanghai',
    miami: 'miami',
    imola: 'imola',
    monaco: 'monaco',
    barcelona: 'barcelona',
    spain: 'barcelona',
    montreal: 'montreal',
    canada: 'montreal',
    silverstone: 'silverstone',
    britain: 'silverstone',
    hungary: 'hungary',
    budapest: 'hungary',
    spa: 'spa',
    belgium: 'spa',
    zandvoort: 'zandvoort',
    monza: 'monza',
    italy: 'monza',
    singapore: 'singapore',
    austin: 'austin',
    mexico: 'mexico',
    'sao paulo': 'interlagos',
    brazil: 'interlagos',
    'las vegas': 'las-vegas',
    qatar: 'qatar',
    'abu dhabi': 'abu-dhabi',
  };
  for (const [key, id] of Object.entries(CIRCUIT_MAP)) {
    if (lower.includes(key)) return id;
  }
  return 'monaco';
}

const AIChatbot: React.FC = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "I am the Apex AI Strategist, powered by the F1 backend. Ask me anything about tire management, undercut opportunities, pit windows, or Grand Prix strategy." }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [simJobId, setSimJobId] = useState<string | null>(null);
  const [simRaceId, setSimRaceId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      // Build conversation history for the backend ChatHistory schema
      const history = messages.slice(1).map(m => ({
        role: m.role,
        content: m.content,
      }));

      const data = await apiFetch<ChatResponse>('/api/v1/llm/chat', {
        method: 'POST',
        body: JSON.stringify({ question: userMessage, history }),
      });

      setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);

      // Use job_id / simulation_race_id returned by the backend
      if (data.job_id && data.simulation_race_id) {
        setSimJobId(data.job_id);
        setSimRaceId(data.simulation_race_id);
      } else if (isSimulationQuestion(userMessage)) {
        // Backend didn't trigger a sim — fall back to client-side detection
        const raceId = extractRaceId(userMessage);
        const jobId = btoa(userMessage.slice(0, 32)).replace(/[^a-z0-9]/gi, '').slice(0, 16);
        setSimJobId(jobId);
        setSimRaceId(raceId);
      }
    } catch (error) {
      console.error('Backend chat error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Backend unavailable: ${error instanceof Error ? error.message : 'Unknown error'}. Ensure the API is running and credentials are set.`,
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic text-white flex items-center gap-3">
          <Bot className="w-10 h-10 text-red-600" />
          AI Strategist
        </h1>
        <p className="text-gray-500 uppercase text-xs tracking-widest mt-2 flex items-center gap-2 font-mono">
          <Sparkles className="w-3 h-3 text-blue-400" /> Powered by {BACKEND_MODEL_LABEL} via Vertex AI
        </p>
      </div>

      {/* Chat Container */}
      <div className="flex-1 rounded-2xl border shadow-2xl overflow-hidden flex flex-col mb-4" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
          <AnimatePresence initial={false}>
            {messages.map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {m.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center flex-shrink-0 shadow-lg mt-1">
                    <Bot className="w-5 h-5 text-white" />
                  </div>
                )}
                <div className={`max-w-[85%] p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${m.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-none'
                  : 'rounded-tl-none border text-gray-200'
                }`} style={{
                  backgroundColor: m.role === 'assistant' ? 'rgba(30, 41, 59, 0.5)' : undefined,
                  borderColor: m.role === 'assistant' ? 'var(--border-color)' : undefined
                }}>
                  {m.content || (isLoading && i === messages.length - 1 ? <Loader2 className="w-4 h-4 animate-spin text-red-600" /> : '')}
                </div>
                {m.role === 'user' && (
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border mt-1" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
                    <User className="w-5 h-5 text-gray-400" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Input Bar — pb-safe anchors above iOS/Android keyboard on mobile */}
        <div className="p-4 pb-[env(safe-area-inset-bottom,1rem)] border-t" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
          <div className="flex gap-4">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Query the strategist... (e.g. 'Is an undercut viable on Lap 18?')"
              aria-label="F1 strategy question for Apex AI"
              maxLength={500}
              className="flex-1 border rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-red-600 transition-all placeholder:text-gray-500 bg-black/20"
              style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="bg-red-600 text-white p-3 rounded-xl hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg"
            >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Race Simulation Panel — shown when a simulation question is detected */}
      {simJobId && simRaceId && (
        <div className="mt-4">
          <RaceSimulator
            jobId={simJobId}
            raceId={simRaceId}
            streamUrl={`/api/v1/simulate/race/stream?job_id=${simJobId}`}
            token=""
            width={500}
            height={340}
          />
        </div>
      )}
    </div>
  );
};

export default AIChatbot;
