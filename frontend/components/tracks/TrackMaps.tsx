/**
 * F1 Circuit Track Maps - SVG Components
 * Visual track layouts for Apex Intelligence Dashboard
 */

import React from 'react';

interface TrackProps {
  width?: number;
  height?: number;
  strokeColor?: string;
  strokeWidth?: number;
  fillColor?: string;
  showSectors?: boolean;
  sectorColors?: [string, string, string];
  showStartFinish?: boolean;
  showDRS?: boolean;
  className?: string;
}

const defaultProps: TrackProps = {
  width: 300,
  height: 200,
  strokeColor: '#FFFFFF',
  strokeWidth: 3,
  fillColor: 'none',
  showSectors: false,
  sectorColors: ['#E10600', '#FFF200', '#00D2BE'],
  showStartFinish: true,
  showDRS: false,
  className: '',
};

// ============================================
// BAHRAIN - Bahrain International Circuit
// ============================================
export const BahrainTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,150 L50,80 Q50,50 80,50 L150,50 Q170,50 170,70 L170,90 Q170,110 190,110 L220,110 Q250,110 250,80 L250,60 Q250,40 230,40 L200,40 Q180,40 180,60 L180,130 Q180,160 210,160 L250,160 Q270,160 270,140 L270,100 Q270,80 250,80 L230,80 M50,150 Q30,150 30,130 L30,100 Q30,80 50,80"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// JEDDAH - Jeddah Corniche Circuit
// ============================================
export const JeddahTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M30,180 L30,50 Q30,30 50,30 L100,30 L100,60 L80,60 L80,80 L120,80 L120,30 L180,30 Q200,30 200,50 L200,100 Q200,120 220,120 L250,120 Q270,120 270,140 L270,180 Q270,190 260,190 L40,190 Q30,190 30,180"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="25" y="175" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MELBOURNE - Albert Park Circuit
// ============================================
export const MelbourneTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M60,170 L60,100 Q60,70 90,70 L130,70 Q150,70 150,50 L150,40 Q150,30 170,30 L230,30 Q260,30 260,60 L260,140 Q260,170 230,170 L200,170 Q180,170 180,150 L180,130 Q180,110 160,110 L120,110 Q100,110 100,130 L100,170 Q100,180 90,180 L70,180 Q60,180 60,170"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="55" y="165" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SUZUKA - Suzuka International Racing Course
// ============================================
export const SuzukaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      {/* Figure-8 layout */}
      <path
        d="M40,120 Q40,80 70,80 L100,80 Q130,80 130,50 Q130,30 160,30 L200,30 Q230,30 230,60 L230,80 Q230,100 210,100 L180,100 Q150,100 150,130 Q150,160 120,160 L80,160 Q50,160 50,130 L50,120 Q50,100 70,100 L150,100 Q180,100 180,130 Q180,160 210,160 L240,160 Q270,160 270,130 L270,80 Q270,50 240,50 L220,50"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="115" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SHANGHAI - Shanghai International Circuit
// ============================================
export const ShanghaiTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,150 L50,80 Q50,50 80,50 L120,50 Q140,50 140,70 L140,90 Q140,110 120,110 Q100,110 100,90 L100,70 Q100,50 130,50 L180,50 Q210,50 210,80 L210,120 Q210,150 240,150 L260,150 Q280,150 280,130 L280,70 Q280,50 260,50 L240,50 Q220,50 220,70 L220,90 Q220,110 200,110 L160,110 Q140,110 140,130 L140,170 Q140,180 130,180 L60,180 Q50,180 50,170 L50,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MIAMI - Miami International Autodrome
// ============================================
export const MiamiTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,160 L40,60 Q40,40 60,40 L180,40 Q200,40 200,60 L200,80 Q200,100 220,100 L250,100 Q270,100 270,120 L270,160 Q270,180 250,180 L60,180 Q40,180 40,160 M200,80 L200,140 Q200,160 180,160 L100,160 Q80,160 80,140 L80,80 Q80,60 100,60 L160,60"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="155" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// IMOLA - Autodromo Enzo e Dino Ferrari
// ============================================
export const ImolaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,100 L80,60 Q100,40 130,40 L200,40 Q230,40 250,60 L270,90 Q280,110 270,130 L240,160 Q220,180 190,180 L100,180 Q70,180 50,160 L30,130 Q20,110 30,90 L50,100"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="95" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MONACO - Circuit de Monaco
// ============================================
export const MonacoTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M60,170 L60,140 Q60,120 80,120 L100,120 Q120,120 120,100 L120,60 Q120,40 140,40 L200,40 Q220,40 220,60 L220,80 Q220,100 240,100 L260,100 Q280,100 280,120 L280,160 Q280,180 260,180 L180,180 Q160,180 160,160 L160,140 Q160,120 140,120 L100,150 Q80,170 60,170"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="55" y="165" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MONTREAL - Circuit Gilles Villeneuve
// ============================================
export const MontrealTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M30,100 L60,100 L80,70 L120,70 L140,100 L180,100 L200,70 L240,70 Q270,70 270,100 L270,130 Q270,160 240,160 L60,160 Q30,160 30,130 L30,100"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="25" y="95" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// BARCELONA - Circuit de Barcelona-Catalunya
// ============================================
export const BarcelonaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,170 L50,80 Q50,50 80,50 L150,50 Q180,50 180,80 L180,100 Q180,120 200,120 L230,120 Q260,120 260,90 L260,60 Q260,40 240,40 L220,60 L200,40 L180,60 L160,40 Q140,40 140,60 L140,140 Q140,170 170,170 L250,170 Q270,170 270,150 L270,130"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="165" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SPIELBERG - Red Bull Ring
// ============================================
export const SpielbergTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,150 L40,80 Q40,50 70,50 L230,50 Q260,50 260,80 L260,100 Q260,130 230,150 L180,180 Q160,190 140,180 L60,150 Q40,140 40,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SILVERSTONE - Silverstone Circuit
// ============================================
export const SilverstoneTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,120 L60,80 Q70,60 90,60 L140,60 Q160,60 170,80 L180,100 L220,100 Q250,100 260,80 L270,60 Q280,40 260,40 L200,40 Q180,40 160,50 L140,40 Q120,30 100,40 L60,60 Q40,70 40,90 L40,150 Q40,170 60,170 L240,170 Q260,170 260,150 L260,130"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="115" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// BUDAPEST - Hungaroring
// ============================================
export const BudapestTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,150 L50,80 Q50,50 80,50 L120,50 Q150,50 150,80 L150,100 Q150,130 180,130 L220,130 Q250,130 250,100 L250,80 Q250,50 220,50 L200,50 Q180,50 180,70 L180,90 Q180,110 160,110 L140,110 Q120,110 120,130 L120,170 Q120,180 110,180 L60,180 Q50,180 50,170 L50,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SPA - Circuit de Spa-Francorchamps
// ============================================
export const SpaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M30,140 L30,100 Q30,70 60,70 L100,50 Q130,30 160,50 L200,80 Q220,100 220,130 L220,150 Q220,170 200,170 L160,170 Q140,170 140,150 L140,120 Q140,100 160,100 L200,100 Q230,100 250,80 L270,50 Q280,30 260,30 L200,30 Q180,30 160,50 L140,30 Q120,20 100,30 L60,60 Q40,70 40,90 L40,140 Q40,160 60,160 L80,160"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="25" y="135" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// ZANDVOORT - Circuit Zandvoort
// ============================================
export const ZandvoortTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,140 L50,80 Q50,50 80,50 L220,50 Q250,50 250,80 L250,100 Q250,130 220,140 L180,150 Q150,160 150,130 L150,100 Q150,80 130,80 L100,80 Q80,80 80,100 L80,160 Q80,180 100,180 L240,180 Q260,180 260,160 L260,140"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="135" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MONZA - Autodromo Nazionale Monza
// ============================================
export const MonzaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,170 L50,60 Q50,30 80,30 L220,30 Q250,30 250,60 L250,80 Q250,100 230,110 L200,130 Q180,140 180,160 L180,180 Q180,190 170,190 L60,190 Q50,190 50,180 L50,170 M200,130 L220,150 Q240,170 260,150 L260,120"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="165" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// SINGAPORE - Marina Bay Street Circuit
// ============================================
export const SingaporeTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,150 L40,60 Q40,40 60,40 L100,40 L100,70 L80,70 L80,100 L120,100 L120,40 L180,40 L180,80 L160,80 L160,100 L200,100 L200,40 L260,40 Q280,40 280,60 L280,160 Q280,180 260,180 L60,180 Q40,180 40,160 L40,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// COTA - Circuit of the Americas
// ============================================
export const COTATrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M30,130 L50,80 Q60,50 90,50 L130,50 Q150,50 150,70 L150,90 Q150,110 170,110 L200,110 Q220,110 230,90 L250,50 Q260,30 280,50 L280,100 Q280,130 250,140 L200,160 Q170,170 140,160 L100,150 Q70,140 60,160 L40,180 Q30,190 30,170 L30,130"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="25" y="125" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MEXICO - Autódromo Hermanos Rodríguez
// ============================================
export const MexicoTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,150 L50,60 Q50,40 70,40 L230,40 Q250,40 250,60 L250,100 Q250,120 230,120 L180,120 Q160,120 160,140 L160,160 Q160,180 140,180 L80,180 Q60,180 60,160 L60,150 Q60,130 80,130 L120,130 Q140,130 140,110 L140,80 Q140,60 120,60 L100,60"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// INTERLAGOS - Autódromo José Carlos Pace
// ============================================
export const InterlagosTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,100 L80,60 Q100,40 130,50 L180,70 Q210,80 230,60 L260,30 Q280,20 280,50 L280,120 Q280,150 250,160 L180,180 Q150,190 120,170 L70,140 Q40,120 50,100"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="95" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// LAS VEGAS - Las Vegas Street Circuit
// ============================================
export const VegasTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,150 L40,50 Q40,30 60,30 L100,30 L100,60 L80,60 L80,100 L140,100 L140,30 L260,30 Q280,30 280,50 L280,170 Q280,190 260,190 L60,190 Q40,190 40,170 L40,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// LUSAIL - Lusail International Circuit
// ============================================
export const LusailTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,140 L50,70 Q50,40 80,40 L180,40 Q210,40 220,70 L240,120 Q250,150 220,160 L160,180 Q130,190 110,170 L80,140 Q60,120 80,100 L120,80 Q140,70 160,80 L200,100 Q220,110 210,130 L180,160"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="135" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// YAS MARINA - Yas Marina Circuit
// ============================================
export const YasMarinaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,150 L50,80 Q50,50 80,50 L200,50 Q230,50 230,80 L230,100 Q230,120 250,120 L270,120 Q280,120 280,140 L280,160 Q280,180 260,180 L160,180 Q140,180 140,160 L140,140 Q140,120 120,120 L100,120 Q80,120 80,140 L80,170 Q80,180 70,180 L60,180 Q50,180 50,170 L50,150"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="145" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// MADRID - Madrid Street Circuit (NEW 2026)
// ============================================
export const MadridTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M40,160 L40,60 Q40,40 60,40 L120,40 Q140,40 150,60 L160,80 L200,80 Q220,80 220,60 L220,50 Q220,30 240,30 L260,30 Q280,30 280,50 L280,150 Q280,170 260,170 L200,170 Q180,170 180,150 L180,130 Q180,110 160,110 L100,110 Q80,110 80,130 L80,170 Q80,180 70,180 L50,180 Q40,180 40,170 L40,160"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="35" y="155" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// BHUJ INDIA - Gujarat International Circuit (Future)
// ============================================
export const BhujTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,140 L50,70 Q50,40 80,40 L150,40 Q180,40 190,60 L210,100 Q220,120 200,140 L170,160 Q150,180 120,170 L90,160 Q70,150 70,130 L70,110 Q70,90 90,90 L140,90 Q160,90 170,110 L180,130 Q190,150 170,160 L130,180 Q100,190 80,170 L60,150 Q50,140 50,140"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="135" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// ARGENTINA - Autódromo Oscar y Juan Gálvez (Buenos Aires)
// ============================================
export const ArgentinaTrack: React.FC<TrackProps> = (props) => {
  const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { ...defaultProps, ...props };
  return (
    <svg width={width} height={height} viewBox="0 0 300 200" className={className}>
      <path
        d="M50,120 L70,80 Q80,60 100,60 L160,60 Q180,60 190,80 L200,100 Q210,120 230,120 L250,120 Q270,120 270,140 L270,160 Q270,180 250,180 L100,180 Q80,180 70,160 L60,140 Q50,120 70,100 L100,80 Q120,60 140,80 L160,100 Q180,120 160,140 L140,160 Q120,180 100,160 L80,140 Q60,120 50,120"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showStartFinish && (
        <rect x="45" y="115" width="15" height="4" fill="#E10600" />
      )}
    </svg>
  );
};

// ============================================
// TRACK REGISTRY - Export all tracks with metadata
// ============================================
export interface TrackInfo {
  id: string;
  name: string;
  country: string;
  component: React.FC<TrackProps>;
  lengthKm: number;
  corners: number;
  drsZones: number;
  laps: number;
}

export const TRACK_REGISTRY: TrackInfo[] = [
  { id: 'bahrain', name: 'Bahrain International Circuit', country: 'Bahrain', component: BahrainTrack, lengthKm: 5.412, corners: 15, drsZones: 3, laps: 57 },
  { id: 'jeddah', name: 'Jeddah Corniche Circuit', country: 'Saudi Arabia', component: JeddahTrack, lengthKm: 6.174, corners: 27, drsZones: 3, laps: 50 },
  { id: 'melbourne', name: 'Albert Park Circuit', country: 'Australia', component: MelbourneTrack, lengthKm: 5.278, corners: 14, drsZones: 4, laps: 58 },
  { id: 'suzuka', name: 'Suzuka International Racing Course', country: 'Japan', component: SuzukaTrack, lengthKm: 5.807, corners: 18, drsZones: 2, laps: 53 },
  { id: 'shanghai', name: 'Shanghai International Circuit', country: 'China', component: ShanghaiTrack, lengthKm: 5.451, corners: 16, drsZones: 2, laps: 56 },
  { id: 'miami', name: 'Miami International Autodrome', country: 'USA', component: MiamiTrack, lengthKm: 5.412, corners: 19, drsZones: 3, laps: 57 },
  { id: 'imola', name: 'Autodromo Enzo e Dino Ferrari', country: 'Italy', component: ImolaTrack, lengthKm: 4.909, corners: 19, drsZones: 2, laps: 63 },
  { id: 'monaco', name: 'Circuit de Monaco', country: 'Monaco', component: MonacoTrack, lengthKm: 3.337, corners: 19, drsZones: 0, laps: 78 },
  { id: 'montreal', name: 'Circuit Gilles Villeneuve', country: 'Canada', component: MontrealTrack, lengthKm: 4.361, corners: 14, drsZones: 2, laps: 70 },
  { id: 'barcelona', name: 'Circuit de Barcelona-Catalunya', country: 'Spain', component: BarcelonaTrack, lengthKm: 4.657, corners: 16, drsZones: 2, laps: 66 },
  { id: 'spielberg', name: 'Red Bull Ring', country: 'Austria', component: SpielbergTrack, lengthKm: 4.318, corners: 10, drsZones: 3, laps: 71 },
  { id: 'silverstone', name: 'Silverstone Circuit', country: 'United Kingdom', component: SilverstoneTrack, lengthKm: 5.891, corners: 18, drsZones: 2, laps: 52 },
  { id: 'budapest', name: 'Hungaroring', country: 'Hungary', component: BudapestTrack, lengthKm: 4.381, corners: 14, drsZones: 2, laps: 70 },
  { id: 'spa', name: 'Circuit de Spa-Francorchamps', country: 'Belgium', component: SpaTrack, lengthKm: 7.004, corners: 19, drsZones: 2, laps: 44 },
  { id: 'zandvoort', name: 'Circuit Zandvoort', country: 'Netherlands', component: ZandvoortTrack, lengthKm: 4.259, corners: 14, drsZones: 2, laps: 72 },
  { id: 'monza', name: 'Autodromo Nazionale Monza', country: 'Italy', component: MonzaTrack, lengthKm: 5.793, corners: 11, drsZones: 2, laps: 53 },
  { id: 'singapore', name: 'Marina Bay Street Circuit', country: 'Singapore', component: SingaporeTrack, lengthKm: 4.940, corners: 19, drsZones: 3, laps: 62 },
  { id: 'cota', name: 'Circuit of the Americas', country: 'USA', component: COTATrack, lengthKm: 5.513, corners: 20, drsZones: 2, laps: 56 },
  { id: 'mexico', name: 'Autódromo Hermanos Rodríguez', country: 'Mexico', component: MexicoTrack, lengthKm: 4.304, corners: 17, drsZones: 3, laps: 71 },
  { id: 'interlagos', name: 'Autódromo José Carlos Pace', country: 'Brazil', component: InterlagosTrack, lengthKm: 4.309, corners: 15, drsZones: 2, laps: 71 },
  { id: 'vegas', name: 'Las Vegas Street Circuit', country: 'USA', component: VegasTrack, lengthKm: 6.201, corners: 17, drsZones: 2, laps: 50 },
  { id: 'lusail', name: 'Lusail International Circuit', country: 'Qatar', component: LusailTrack, lengthKm: 5.419, corners: 16, drsZones: 2, laps: 57 },
  { id: 'yas_marina', name: 'Yas Marina Circuit', country: 'UAE', component: YasMarinaTrack, lengthKm: 5.281, corners: 16, drsZones: 2, laps: 58 },
  { id: 'madrid', name: 'Madrid Street Circuit', country: 'Spain', component: MadridTrack, lengthKm: 5.474, corners: 18, drsZones: 2, laps: 55 },
  { id: 'bhuj', name: 'Gujarat International Circuit', country: 'India', component: BhujTrack, lengthKm: 5.340, corners: 16, drsZones: 3, laps: 57 },
  { id: 'argentina', name: 'Autódromo Oscar y Juan Gálvez', country: 'Argentina', component: ArgentinaTrack, lengthKm: 4.259, corners: 15, drsZones: 2, laps: 72 },
];

// ============================================
// HELPER: Get track component by ID
// ============================================
export const getTrackById = (id: string): TrackInfo | undefined => {
  return TRACK_REGISTRY.find(track => track.id === id);
};

// ============================================
// DEFAULT EXPORT: Track selector component
// ============================================
interface TrackDisplayProps extends TrackProps {
  trackId: string;
}

export const TrackDisplay: React.FC<TrackDisplayProps> = ({ trackId, ...props }) => {
  const track = getTrackById(trackId);
  if (!track) return null;
  const TrackComponent = track.component;
  return <TrackComponent {...props} />;
};

export default TrackDisplay;
