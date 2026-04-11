import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lock, X } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

const AdminModal: React.FC = () => {
  const { adminLogin, isAdminModalOpen, setAdminModalOpen } = useAppStore();
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const success = adminLogin(password);
    if (success) {
      setAdminModalOpen(false);
      setPassword('');
      setError(false);
    } else {
      setError(true);
      setTimeout(() => setError(false), 2000);
    }
  };

  return (
    <AnimatePresence>
      {isAdminModalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-6">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setAdminModalOpen(false)}
            className="absolute inset-0 bg-black/90 backdrop-blur-2xl"
          />

          {/* Modal Content */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="relative w-full max-w-sm glass-morphism p-8 rounded-[32px] border-red-500/20 shadow-[0_0_50px_rgba(225,6,0,0.1)] bg-black/40"
          >
            <button
              onClick={() => setAdminModalOpen(false)}
              className="absolute top-6 right-6 p-2 rounded-full hover:bg-white/10 transition-colors text-white/40 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="text-center mb-8">
              <div className="w-12 h-12 bg-red-600/20 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-red-500/20 shadow-lg shadow-red-900/20">
                <Lock className="w-6 h-6 text-red-500" />
              </div>
              <h3 className="text-xl font-display font-bold italic uppercase tracking-tight text-white mb-1">Administrative Access</h3>
              <p className="text-white/40 text-[10px] font-black uppercase tracking-widest">Authorized Personnel Only</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="relative">
                <input
                  type="password"
                  autoFocus
                  placeholder="Security Credential"
                  className={`w-full px-6 py-4 rounded-2xl bg-white/5 border ${
                    error ? 'border-red-600 animate-shake' : 'border-white/10'
                  } focus:border-red-600 outline-none transition-all text-sm text-center placeholder:text-white/20 text-white`}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {error && (
                <motion.p
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-red-500 text-[10px] font-black uppercase tracking-widest text-center"
                >
                  Auth Failed: System Locked
                </motion.p>
              )}

              <button
                type="submit"
                className="w-full py-4 rounded-xl bg-red-600 text-white font-black uppercase tracking-widest text-xs hover:bg-red-700 transition-all shadow-lg shadow-red-900/40 active:scale-[0.98]"
              >
                Confirm Terminal Access
              </button>
            </form>

            <button
              onClick={() => setAdminModalOpen(false)}
              className="w-full mt-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/20 hover:text-white/40 transition-colors"
            >
              Cancel Initialization
            </button>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default AdminModal;
