/**
 * @file components/ConnectionBadge.tsx
 * @description Displays live/mock backend connection status in the UI.
 */

import React from 'react';
import { Wifi, WifiOff } from 'lucide-react';

interface ConnectionBadgeProps {
  isLive: boolean;
  latency?: number | null;
  className?: string;
}

const ConnectionBadge: React.FC<ConnectionBadgeProps> = ({ isLive, latency, className = '' }) => {
  if (isLive) {
    return (
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-500/10 border border-green-500/20 ${className}`}>
        <Wifi className="w-3 h-3 text-green-500" />
        <span className="text-[9px] font-bold text-green-500 uppercase tracking-wider">
          Live API{latency ? ` (${latency}ms)` : ''}
        </span>
      </div>
    );
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/20 ${className}`}>
      <WifiOff className="w-3 h-3 text-yellow-500" />
      <span className="text-[9px] font-bold text-yellow-500 uppercase tracking-wider">
        Mock Data
      </span>
    </div>
  );
};

export default ConnectionBadge;
