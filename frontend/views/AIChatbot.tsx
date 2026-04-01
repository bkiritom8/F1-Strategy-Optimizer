import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, User, Bot, Loader2, Info, Sparkles } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const SYSTEM_PROMPT = `You are an elite F1 Race Engineer and Strategist for 'Apex Intelligence', an advanced race strategy platform. Your knowledge covers tire physics, aerodynamics, historical F1 data, and real-time tactical decisions. Be technical, concise, and analytical. Use professional racing terminology (e.g., 'thermals', 'dirty air', 'box-to-box', 'overcut', 'undercut', 'stint length', 'degradation curve'). Reference real drivers, circuits, and historical races when relevant. Format key data points clearly.`;

/**
 * Gemini model to use. gemini-2.0-flash-lite is the cheapest option
 * at $0.00 per 1M tokens (free tier) or minimal cost beyond that.
 */
const GEMINI_MODEL = 'gemini-2.0-flash-lite';

const AIChatbot: React.FC = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "I am the Apex AI Strategist, powered by Google Gemini. Ask me anything about tire management, undercut opportunities, pit windows, or car setup for any Grand Prix." }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY;

    if (!apiKey || apiKey === 'PLACEHOLDER_API_KEY') {
      setMessages(prev => [...prev,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: "Gemini API key not configured. Set VITE_GEMINI_API_KEY in your .env.local file. You can get a free key at https://aistudio.google.com/apikey" }
      ]);
      setInput('');
      return;
    }

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      // Build conversation history for Gemini format
      const history = messages.slice(1).map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }],
      }));

      const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:streamGenerateContent?alt=sse&key=${apiKey}`;

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_instruction: { parts: [{ text: SYSTEM_PROMPT }] },
          contents: [
            ...history,
            { role: 'user', parts: [{ text: userMessage }] },
          ],
          generationConfig: {
            maxOutputTokens: 800,
            temperature: 0.7,
            topP: 0.95,
          },
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Gemini API error ${response.status}: ${errText.slice(0, 200)}`);
      }

      if (!response.body) throw new Error('No response body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let fullResponse = '';
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(line => line.trim() !== '');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            if (jsonStr === '[DONE]') continue;
            try {
              const data = JSON.parse(jsonStr);
              const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
              if (text) {
                fullResponse += text;
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = { role: 'assistant', content: fullResponse };
                  return updated;
                });
              }
            } catch (_parseErr) {
              // Incomplete JSON chunk during streaming, skip
            }
          }
        }
      }
    } catch (error) {
      console.error('Gemini API Error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Connection error: ${error instanceof Error ? error.message : 'Unknown error'}. Check your API key and network.`
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
          <Sparkles className="w-3 h-3 text-blue-400" /> Powered by Google Gemini ({GEMINI_MODEL})
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
    </div>
  );
};

export default AIChatbot;
