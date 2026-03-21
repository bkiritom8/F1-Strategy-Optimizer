import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { BrainCircuit, Loader2 } from 'lucide-react';
import { COLORS } from '../constants';

const AIStrategist: React.FC = () => {
    const [response, setResponse] = useState('');
    const [loading, setLoading] = useState(false);
    const initialized = useRef(false);

    useEffect(() => {
        if (initialized.current) return;
        initialized.current = true;

        const fetchStrategy = async () => {
            setLoading(true);
            try {
                const res = await fetch("/api/nvidia/v1/chat/completions", {
                    method: "POST",
                    headers: {
                        "Authorization": "Bearer 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",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream"
                    },
                    body: JSON.stringify({
                        model: "moonshotai/kimi-k2.5",
                        messages: [{ role: "user", content: "Provide a brief, 3-sentence F1 race strategy advice for Max Verstappen running P1 in Monaco with Medium tires on lap 23/78. Address the user directly as 'Strategist'. Keep it focused on immediate telemetry concerns (like undercuts or tire cliff)." }],
                        max_tokens: 300,
                        temperature: 0.7,
                        top_p: 1.0,
                        stream: true,
                        chat_template_kwargs: { thinking: true }
                    })
                });

                if (!res.body) return;
                const reader = res.body.getReader();
                const decoder = new TextDecoder("utf-8");

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split("\n").filter(line => line.trim() !== "");
                    for (const line of lines) {
                        if (line.replace(/^data: /, "") === "[DONE]") {
                            setLoading(false);
                            return;
                        }
                        if (line.startsWith("data: ")) {
                            try {
                                const data = JSON.parse(line.replace(/^data: /, ""));
                                if (data.choices[0].delta.content) {
                                    setResponse(prev => prev + data.choices[0].delta.content);
                                }
                            } catch (e) {
                                // Ignore parse errors from incomplete chunks in stream
                            }
                        }
                    }
                }
            } catch (error) {
                console.error("AI fetch error:", error);
            }
            setLoading(false);
        };

        fetchStrategy();
    }, []);

    return (
        <div className="rounded-xl p-6 border shadow-xl flex flex-col h-[350px]" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <div className="flex items-center justify-between mb-4 border-b pb-4" style={{ borderColor: 'var(--border-color)' }}>
                <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400 flex items-center gap-2">
                    <BrainCircuit className="w-5 h-5" style={{ color: COLORS.accent.green }} />
                    NVIDIA AI Strategist
                </h3>
                {loading && (
                    <div className="flex items-center gap-2">
                        <span className="text-[10px] uppercase font-mono animate-pulse" style={{ color: COLORS.accent.green }}>Analyzing Telemetry...</span>
                        <Loader2 className="w-4 h-4 animate-spin" style={{ color: COLORS.accent.green }} />
                    </div>
                )}
            </div>
            <div className="flex-1 overflow-y-auto text-sm text-gray-300 font-mono leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.5 }}
                >
                    {response || "Initializing neural network pipeline..."}
                    {loading && <span className="inline-block w-2 h-4 ml-1 animate-ping align-middle" style={{ backgroundColor: COLORS.accent.green }} />}
                </motion.div>
            </div>
        </div>
    );
};

export default AIStrategist;
