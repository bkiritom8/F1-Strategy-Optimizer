/**
 * Track Gallery - Display all F1 circuits in a grid
 * Use this component to show all available tracks in the dashboard
 */

import React, { useState, memo } from 'react';
import { motion } from 'framer-motion';
import { TRACK_REGISTRY, TrackInfo } from './TrackMaps';
import { COLORS } from '../../constants';

interface TrackGalleryProps {
  onTrackSelect?: (track: TrackInfo) => void;
  selectedTrackId?: string;
  columns?: 2 | 3 | 4;
  showDetails?: boolean;
}

interface TrackItemProps {
  track: TrackInfo;
  isSelected: boolean;
  onSelect?: (track: TrackInfo) => void;
  showDetails: boolean;
}

const TrackItem = memo(({ track, isSelected, onSelect, showDetails }: TrackItemProps) => {
  const [isHovered, setIsHovered] = useState(false);

  const bgColor = COLORS.dark.secondary;
  const textColor = COLORS.dark.text;
  const textSecondary = COLORS.dark.textSecondary;
  const borderColor = 'rgba(255,255,255,0.1)';

  const TrackComponent = track.component;

  const itemVariants = {
    hidden: { opacity: 0, scale: 0.95, y: 15 },
    visible: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.3 } }
  };

  return (
    <motion.div
      variants={itemVariants}
      onClick={() => onSelect?.(track)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        backgroundColor: bgColor,
        borderRadius: '12px',
        padding: '16px',
        cursor: onSelect ? 'pointer' : 'default',
        border: `2px solid ${isSelected ? COLORS.accent.red : isHovered ? COLORS.accent.green : borderColor}`,
        transition: 'all 0.2s ease',
        transform: isHovered && !isSelected ? 'scale(1.02)' : 'scale(1)',
        boxShadow: isSelected ? `0 0 20px ${COLORS.accent.red}40` : 'none',
        position: 'relative',
        zIndex: isHovered || isSelected ? 10 : 1,
      }}
    >
      {/* No-data badge for speculative / future circuits */}
      {!track.hasLiveData && (
        <div
          title={track.statusNote ?? 'No FastF1 telemetry data available for this circuit.'}
          style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            backgroundColor: 'rgba(251, 191, 36, 0.15)',
            border: '1px solid rgba(251, 191, 36, 0.5)',
            borderRadius: '6px',
            padding: '3px 7px',
            fontSize: '10px',
            fontWeight: 700,
            color: '#FBBF24',
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
            cursor: 'help',
            zIndex: 5,
          }}
          aria-label={`No telemetry: ${track.statusNote ?? ''}`}
          data-testid="no-data-badge"
        >
          <svg width="10" height="10" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          Approx. Layout
        </div>
      )}

      {/* Track SVG */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          marginBottom: '12px',
          padding: '8px',
          backgroundColor: 'rgba(0,0,0,0.3)',
          borderRadius: '8px',
        }}
      >
        <TrackComponent
          width={180}
          height={120}
          strokeColor={isSelected ? COLORS.accent.red : isHovered ? COLORS.accent.green : textColor}
          strokeWidth={2.5}
          showStartFinish={true}
          animated={isHovered || isSelected}
        />
      </div>

      {/* Track Name */}
      <h3
        style={{
          margin: 0,
          fontSize: '14px',
          fontWeight: 700,
          color: textColor,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {track.name}
      </h3>

      {/* Country */}
      <p
        style={{
          margin: '4px 0 0 0',
          fontSize: '12px',
          color: textSecondary,
        }}
      >
        {track.country}
      </p>

      {/* Track Details */}
      {showDetails && (
        <div
          style={{
            display: 'flex',
            gap: '12px',
            marginTop: '12px',
            paddingTop: '12px',
            borderTop: `1px solid ${borderColor}`,
          }}
        >
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: textColor }}>
              {track.lengthKm}
            </div>
            <div style={{ fontSize: '10px', color: textSecondary, textTransform: 'uppercase' }}>
              km
            </div>
          </div>
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: textColor }}>
              {track.corners}
            </div>
            <div style={{ fontSize: '10px', color: textSecondary, textTransform: 'uppercase' }}>
              corners
            </div>
          </div>
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: COLORS.accent.green }}>
              {track.drsZones}
            </div>
            <div style={{ fontSize: '10px', color: textSecondary, textTransform: 'uppercase' }}>
              DRS
            </div>
          </div>
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: COLORS.accent.purple }}>
              {track.laps}
            </div>
            <div style={{ fontSize: '10px', color: textSecondary, textTransform: 'uppercase' }}>
              Laps
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
});

export const TrackGallery: React.FC<TrackGalleryProps> = ({
  onTrackSelect,
  selectedTrackId,
  columns = 3,
  showDetails = true,
}) => {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.05 }
    }
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className={`grid gap-4 p-4 ${
        columns === 2 ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-2' : 
        columns === 3 ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3' : 
        'grid-cols-1 md:grid-cols-2 lg:grid-cols-4'
      }`}
    >
      {TRACK_REGISTRY.map((track) => (
        <TrackItem
          key={track.id}
          track={track}
          isSelected={selectedTrackId === track.id}
          onSelect={onTrackSelect}
          showDetails={showDetails}
        />
      ))}
    </motion.div>
  );
};

export default TrackGallery;
