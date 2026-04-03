/**
 * Track Detail Card - Detailed view of a single circuit
 * Shows track layout, stats, and characteristics
 */

import React from 'react';
import { TrackInfo, getTrackById } from './TrackMaps';
import { COLORS } from '../../constants';

interface TrackDetailCardProps {
  trackId: string;
  showFullStats?: boolean;
  onClose?: () => void;
}

// Extended track data with additional info
const TRACK_EXTENDED_DATA: Record<string, {
  lapRecord: string;
  recordHolder: string;
  recordYear: number;
  tireWear: 'low' | 'medium' | 'high';
  fuelConsumption: 'low' | 'medium' | 'high';
  overtaking: 'low' | 'medium' | 'high';
  firstGP: number;
}> = {
  bahrain: { lapRecord: '1:31.447', recordHolder: 'Pedro de la Rosa', recordYear: 2005, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'high', firstGP: 2004 },
  jeddah: { lapRecord: '1:30.734', recordHolder: 'Lewis Hamilton', recordYear: 2021, tireWear: 'low', fuelConsumption: 'high', overtaking: 'medium', firstGP: 2021 },
  melbourne: { lapRecord: '1:20.235', recordHolder: 'Charles Leclerc', recordYear: 2024, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'high', firstGP: 1996 },
  suzuka: { lapRecord: '1:30.983', recordHolder: 'Lewis Hamilton', recordYear: 2019, tireWear: 'high', fuelConsumption: 'high', overtaking: 'low', firstGP: 1987 },
  shanghai: { lapRecord: '1:32.238', recordHolder: 'Michael Schumacher', recordYear: 2004, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2004 },
  miami: { lapRecord: '1:29.708', recordHolder: 'Max Verstappen', recordYear: 2023, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2022 },
  imola: { lapRecord: '1:15.484', recordHolder: 'Lewis Hamilton', recordYear: 2020, tireWear: 'medium', fuelConsumption: 'low', overtaking: 'low', firstGP: 1980 },
  monaco: { lapRecord: '1:12.909', recordHolder: 'Lewis Hamilton', recordYear: 2021, tireWear: 'low', fuelConsumption: 'low', overtaking: 'low', firstGP: 1950 },
  montreal: { lapRecord: '1:13.078', recordHolder: 'Valtteri Bottas', recordYear: 2019, tireWear: 'low', fuelConsumption: 'medium', overtaking: 'high', firstGP: 1978 },
  barcelona: { lapRecord: '1:18.149', recordHolder: 'Max Verstappen', recordYear: 2021, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'low', firstGP: 1991 },
  spielberg: { lapRecord: '1:05.619', recordHolder: 'Carlos Sainz', recordYear: 2020, tireWear: 'low', fuelConsumption: 'low', overtaking: 'high', firstGP: 1970 },
  silverstone: { lapRecord: '1:27.097', recordHolder: 'Max Verstappen', recordYear: 2020, tireWear: 'high', fuelConsumption: 'high', overtaking: 'medium', firstGP: 1950 },
  budapest: { lapRecord: '1:16.627', recordHolder: 'Lewis Hamilton', recordYear: 2020, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'low', firstGP: 1986 },
  spa: { lapRecord: '1:46.286', recordHolder: 'Valtteri Bottas', recordYear: 2018, tireWear: 'medium', fuelConsumption: 'high', overtaking: 'high', firstGP: 1950 },
  zandvoort: { lapRecord: '1:11.097', recordHolder: 'Lewis Hamilton', recordYear: 2021, tireWear: 'high', fuelConsumption: 'low', overtaking: 'low', firstGP: 1952 },
  monza: { lapRecord: '1:21.046', recordHolder: 'Rubens Barrichello', recordYear: 2004, tireWear: 'low', fuelConsumption: 'high', overtaking: 'high', firstGP: 1950 },
  singapore: { lapRecord: '1:35.867', recordHolder: 'Lewis Hamilton', recordYear: 2023, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'low', firstGP: 2008 },
  cota: { lapRecord: '1:36.169', recordHolder: 'Charles Leclerc', recordYear: 2019, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2012 },
  mexico: { lapRecord: '1:17.774', recordHolder: 'Valtteri Bottas', recordYear: 2021, tireWear: 'low', fuelConsumption: 'low', overtaking: 'medium', firstGP: 1963 },
  interlagos: { lapRecord: '1:10.540', recordHolder: 'Valtteri Bottas', recordYear: 2018, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'high', firstGP: 1973 },
  vegas: { lapRecord: '1:35.490', recordHolder: 'Oscar Piastri', recordYear: 2023, tireWear: 'low', fuelConsumption: 'high', overtaking: 'high', firstGP: 2023 },
  lusail: { lapRecord: '1:24.319', recordHolder: 'Max Verstappen', recordYear: 2023, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2021 },
  yas_marina: { lapRecord: '1:26.103', recordHolder: 'Max Verstappen', recordYear: 2021, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2009 },
  madrid: { lapRecord: 'TBD', recordHolder: 'TBD', recordYear: 2026, tireWear: 'medium', fuelConsumption: 'medium', overtaking: 'high', firstGP: 2026 },
  bhuj: { lapRecord: 'TBD', recordHolder: 'TBD', recordYear: 2027, tireWear: 'high', fuelConsumption: 'medium', overtaking: 'medium', firstGP: 2027 },
  argentina: { lapRecord: '1:27.981', recordHolder: 'Gerhard Berger', recordYear: 1997, tireWear: 'medium', fuelConsumption: 'low', overtaking: 'medium', firstGP: 1953 },
};

const getRatingColor = (rating: 'low' | 'medium' | 'high') => {
  switch (rating) {
    case 'low': return COLORS.accent.green;
    case 'medium': return COLORS.accent.yellow;
    case 'high': return COLORS.accent.red;
  }
};

const getRatingLabel = (rating: 'low' | 'medium' | 'high') => {
  switch (rating) {
    case 'low': return 'Low';
    case 'medium': return 'Medium';
    case 'high': return 'High';
  }
};

export const TrackDetailCard: React.FC<TrackDetailCardProps> = ({
  trackId,
  showFullStats = true,
  onClose,
}) => {
  const track = getTrackById(trackId);
  const extendedData = TRACK_EXTENDED_DATA[trackId];

  if (!track) return null;

  const TrackComponent = track.component;
  const bgColor = COLORS.dark.secondary;
  const bgTertiary = COLORS.dark.tertiary;
  const textColor = COLORS.dark.text;
  const textSecondary = COLORS.dark.textSecondary;
  const borderColor = 'rgba(255,255,255,0.1)';

  return (
    <div
      style={{
        backgroundColor: bgColor,
        borderRadius: '16px',
        padding: '24px',
        border: `1px solid ${borderColor}`,
        position: 'relative',
      }}
    >
      {/* Close Button */}
      {onClose && (
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            background: 'none',
            border: 'none',
            color: textSecondary,
            cursor: 'pointer',
            fontSize: '24px',
            lineHeight: 1,
          }}
        >
          ×
        </button>
      )}

      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <h2
          style={{
            margin: 0,
            fontSize: '24px',
            fontWeight: 800,
            color: textColor,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            fontStyle: 'italic',
          }}
        >
          {track.name}
        </h2>
        <p style={{ margin: '4px 0 0 0', color: textSecondary, fontSize: '14px' }}>
          {track.country} • First GP: {extendedData?.firstGP || 'N/A'}
        </p>
      </div>

      {/* Track SVG - Large */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '24px',
          backgroundColor: bgTertiary,
          borderRadius: '12px',
          marginBottom: '20px',
        }}
      >
        <TrackComponent
          width={320}
          height={200}
          strokeColor={COLORS.accent.red}
          strokeWidth={4}
          showStartFinish={true}
          animated={true}
        />
      </div>

      {/* Stats Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '12px',
          marginBottom: '20px',
        }}
      >
        <div style={{ textAlign: 'center', padding: '10px 8px', backgroundColor: bgTertiary, borderRadius: '8px' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: textColor }}>{track.lengthKm}</div>
          <div style={{ fontSize: '9px', fontWeight: 700, color: textSecondary, textTransform: 'uppercase', marginTop: '4px' }}>Length (km)</div>
        </div>
        <div style={{ textAlign: 'center', padding: '10px 8px', backgroundColor: bgTertiary, borderRadius: '8px' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: textColor }}>{track.corners}</div>
          <div style={{ fontSize: '9px', fontWeight: 700, color: textSecondary, textTransform: 'uppercase', marginTop: '4px' }}>Corners</div>
        </div>
        <div style={{ textAlign: 'center', padding: '10px 8px', backgroundColor: bgTertiary, borderRadius: '8px' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: COLORS.accent.green }}>{track.drsZones}</div>
          <div style={{ fontSize: '9px', fontWeight: 700, color: textSecondary, textTransform: 'uppercase', marginTop: '4px' }}>DRS</div>
        </div>
        <div style={{ textAlign: 'center', padding: '10px 8px', backgroundColor: bgTertiary, borderRadius: '8px' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: COLORS.accent.blue }}>{track.laps}</div>
          <div style={{ fontSize: '9px', fontWeight: 700, color: textSecondary, textTransform: 'uppercase', marginTop: '4px' }}>Laps</div>
        </div>
        <div style={{ textAlign: 'center', padding: '10px 8px', backgroundColor: bgTertiary, borderRadius: '8px' }}>
          <div style={{ fontSize: '16px', fontWeight: 700, color: COLORS.accent.purple }}>{extendedData?.lapRecord || '-'}</div>
          <div style={{ fontSize: '9px', fontWeight: 700, color: textSecondary, textTransform: 'uppercase', marginTop: '4px' }}>Lap Record</div>
        </div>
      </div>

      {/* Lap Record Holder */}
      {extendedData && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: bgTertiary,
            borderRadius: '8px',
            marginBottom: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ color: textSecondary, fontSize: '13px' }}>Lap Record Holder</span>
          <span style={{ color: textColor, fontWeight: 600 }}>
            {extendedData.recordHolder} ({extendedData.recordYear})
          </span>
        </div>
      )}

      {/* Characteristics */}
      {showFullStats && extendedData && (
        <div>
          <h4
            style={{
              margin: '0 0 12px 0',
              fontSize: '12px',
              fontWeight: 700,
              color: textSecondary,
              textTransform: 'uppercase',
              letterSpacing: '1px',
            }}
          >
            Track Characteristics
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 14px',
                backgroundColor: bgTertiary,
                borderRadius: '8px',
              }}
            >
              <span style={{ color: textSecondary, fontSize: '13px' }}>Tire Wear</span>
              <span
                style={{
                  color: getRatingColor(extendedData.tireWear),
                  fontWeight: 700,
                  fontSize: '13px',
                }}
              >
                {getRatingLabel(extendedData.tireWear)}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 14px',
                backgroundColor: bgTertiary,
                borderRadius: '8px',
              }}
            >
              <span style={{ color: textSecondary, fontSize: '13px' }}>Fuel Consumption</span>
              <span
                style={{
                  color: getRatingColor(extendedData.fuelConsumption),
                  fontWeight: 700,
                  fontSize: '13px',
                }}
              >
                {getRatingLabel(extendedData.fuelConsumption)}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 14px',
                backgroundColor: bgTertiary,
                borderRadius: '8px',
              }}
            >
              <span style={{ color: textSecondary, fontSize: '13px' }}>Overtaking Difficulty</span>
              <span
                style={{
                  color: getRatingColor(extendedData.overtaking),
                  fontWeight: 700,
                  fontSize: '13px',
                }}
              >
                {getRatingLabel(extendedData.overtaking)}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TrackDetailCard;
