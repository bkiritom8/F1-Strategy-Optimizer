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
  theme?: 'dark' | 'light';
}

interface TrackItemProps {
  track: TrackInfo;
  isSelected: boolean;
  onSelect?: (track: TrackInfo) => void;
  theme: 'dark' | 'light';
  showDetails: boolean;
}

const TrackItem = memo(({ track, isSelected, onSelect, theme, showDetails }: TrackItemProps) => {
  const [isHovered, setIsHovered] = useState(false);

  const bgColor = theme === 'dark' ? COLORS.dark.secondary : COLORS.light.secondary;
  const textColor = theme === 'dark' ? COLORS.dark.text : COLORS.light.text;
  const textSecondary = theme === 'dark' ? COLORS.dark.textSecondary : COLORS.light.textSecondary;
  const borderColor = theme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';

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
      {/* Track SVG */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          marginBottom: '12px',
          padding: '8px',
          backgroundColor: theme === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)',
          borderRadius: '8px',
        }}
      >
        <TrackComponent
          width={180}
          height={120}
          strokeColor={isSelected ? COLORS.accent.red : isHovered ? COLORS.accent.green : textColor}
          strokeWidth={2.5}
          showStartFinish={true}
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
  theme = 'dark',
}) => {
  const gridCols = {
    2: 'repeat(2, 1fr)',
    3: 'repeat(3, 1fr)',
    4: 'repeat(4, 1fr)',
  };

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
      style={{
        display: 'grid',
        gridTemplateColumns: gridCols[columns],
        gap: '16px',
        padding: '16px',
      }}
    >
      {TRACK_REGISTRY.map((track) => (
        <TrackItem
          key={track.id}
          track={track}
          isSelected={selectedTrackId === track.id}
          onSelect={onTrackSelect}
          theme={theme}
          showDetails={showDetails}
        />
      ))}
    </motion.div>
  );
};

export default TrackGallery;
