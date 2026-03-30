import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, User, Bot, Loader2, Info } from 'lucide-react';
import { COLORS } from '../constants';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const AIChatbot: React.FC = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "I am the Apex AI Strategist. Ask me anything about tire management, undercut opportunities, or car setup for this weekend's Grand Prix." }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  /**
   * Sends user prompt to NVIDIA API and streams the response.
   */
  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    const apiKey = (process.env as any).VITE_NVIDIA_API_KEY;

    if (!apiKey) {
      setMessages(prev => [...prev, 
        { role: 'user', content: userMessage },
        { role: 'assistant', content: "NVIDIA API Key not found. Please set VITE_NVIDIA_API_KEY in your environment configuration." }
      ]);
      setInput('');
      return;
    }

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/nvidia/v1/chat/completions", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${apiKey}`,
          "Content-Type": "application/json",
          "Accept": "text/event-stream"
        },
        body: JSON.stringify({
          model: "moonshotai/kimi-k2.5",
          messages: [
            { role: "system", content: "You are an elite F1 Race Engineer and Strategist for 'Apex Intelligence'. Your knowledge covers tire physics, aerodynamics, historical data, and real-time tactical decisions. Be technical, concise, and analytical. Use professional racing terminology (e.g., 'thermals', 'dirty air', 'box-to-box', 'overcut')." },
            ...messages.slice(1).map(m => ({ role: m.role, content: m.content })),
            { role: "user", content: userMessage }
          ],
          max_tokens: 500,
          temperature: 0.7,
          top_p: 1.0,
          stream: true,
          chat_template_kwargs: { thinking: true }
        })
      });

      if (!response.body) throw new Error("No response body");
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let fullResponse = "";
      setMessages(prev => [...prev, { role: 'assistant', content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n").filter(line => line.trim() !== "");
        for (const line of lines) {
          if (line.replace(/^data: /, "") === "[DONE]") {
            setIsLoading(false);
            return;
          }
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.replace(/^data: /, ""));
              if (data.choices[0].delta.content) {
                fullResponse += data.choices[0].delta.content;
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  return [...prev.slice(0, -1), { ...last, content: fullResponse }];
                });
              }
            } catch (e) {
              // Ignore incomplete JSON chunks stream
            }
          }
        }
      }
    } catch (error) {
      console.error("AI Error:", error);
      setMessages(prev => [...prev, { role: 'assistant', content: "Error connecting to strategic link. Check API configuration." }]);
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
          <Info className="w-3 h-3" /> Powered by NVIDIA NIM Models
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
                <div className={`max-w-[85%] p-4 rounded-2xl text-sm leading-relaxed shadow-sm font-mono ${m.role === 'user'
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

        {/* Input Bar */}
        <div className="p-4 border-t" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
          <form
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="flex gap-4"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Query the strategist... (e.g. 'Is an undercut viable on Lap 18?')"
              className="flex-1 border rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-red-600 transition-all placeholder:text-gray-500 bg-black/20"
              style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="bg-red-600 text-white p-3 rounded-xl hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg"
            >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AIChatbot;

