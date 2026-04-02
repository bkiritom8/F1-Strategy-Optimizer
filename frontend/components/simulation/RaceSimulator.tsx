import React, { useEffect, useRef, useState, useCallback } from 'react';
import { TEAM_COLORS } from '../../constants';
import { getTrackById } from '../tracks/TrackMaps';

// SSE frame types
interface CarFrame {
  id: string;
  track_pct: number;   // 0.0–1.0 fraction of lap completed
  position: number;
  compound: 'SOFT' | 'MEDIUM' | 'HARD' | 'INTERMEDIATE' | 'WET';
  gap_ms: number;
  lap_time_ms: number;
  tire_age: number;
}

interface LapFrame {
  event: 'sim_lap';
  lap: number;
  cars: CarFrame[];
}

interface CompleteFrame {
  event: 'sim_complete';
  p10_finish: number;
  p50_finish: number;
  p90_finish: number;
  llm_context: {
    winner: string;
    fastest_lap: string;
    safety_cars: number;
    total_pit_stops: number;
  };
}

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#E8002D',
  MEDIUM: '#FFF200',
  HARD: '#FFFFFF',
  INTERMEDIATE: '#39B54A',
  WET: '#0067FF',
};

const PLAYBACK_DURATION_MS = 30_000; // 30 seconds always

interface Props {
  jobId: string;
  raceId: string;
  streamUrl: string;    // e.g. /api/v1/simulate/race/stream?job_id=xxx
  token: string;        // JWT for auth header (passed via EventSource polyfill or fetch)
  width?: number;
  height?: number;
}

export const RaceSimulator: React.FC<Props> = ({
  jobId,
  raceId,
  streamUrl,
  token,
  width = 600,
  height = 400,
}) => {
  const [allLaps, setAllLaps] = useState<CarFrame[][]>([]);
  const [currentLapIdx, setCurrentLapIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [summary, setSummary] = useState<CompleteFrame | null>(null);
  const [hoveredCar, setHoveredCar] = useState<CarFrame | null>(null);

  const trackRef = useRef<SVGPathElement | null>(null);
  const animRef = useRef<number | null>(null);

  // ---------- Stream consumption ----------
  useEffect(() => {
    const laps: CarFrame[][] = [];
    let done = false;

    const consume = async () => {
      try {
        const headers: HeadersInit = { 'Content-Type': 'application/json' };
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
        const resp = await fetch(streamUrl, { headers });
        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (!done) {
          const { value, done: streamDone } = await reader.read();
          if (streamDone) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n\n');
          buf = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const frame = JSON.parse(line.slice(6));
              if (frame.event === 'sim_lap') {
                laps.push((frame as LapFrame).cars);
                setAllLaps([...laps]);
              } else if (frame.event === 'sim_complete') {
                setSummary(frame as CompleteFrame);
                setIsLoading(false);
                setIsPlaying(true);
                done = true;
              } else if (frame.event === 'done' || frame.event === 'error') {
                setIsLoading(false);
                done = true;
              }
            } catch {
              // skip malformed frame
            }
          }
        }
      } catch (err) {
        console.error('Simulation stream error:', err);
        setIsLoading(false);
      }
    };

    consume();
    return () => { done = true; };
  }, [streamUrl, token]);

  // ---------- Playback animation ----------
  useEffect(() => {
    if (!isPlaying || allLaps.length === 0) return;

    const totalLaps = allLaps.length;
    const frameInterval = PLAYBACK_DURATION_MS / totalLaps;
    let frame = 0;

    const tick = () => {
      setCurrentLapIdx(frame);
      frame = (frame + 1) % totalLaps;
      animRef.current = window.setTimeout(tick, frameInterval);
    };

    animRef.current = window.setTimeout(tick, frameInterval);
    return () => { if (animRef.current) clearTimeout(animRef.current); };
  }, [isPlaying, allLaps.length]);

  // ---------- Position calculation ----------
  const getCarPosition = useCallback(
    (trackPct: number): { x: number; y: number } => {
      const path = trackRef.current;
      if (!path) return { x: width / 2, y: height / 2 };
      const totalLength = path.getTotalLength();
      const point = path.getPointAtLength(trackPct * totalLength);
      // Scale from SVG viewBox (300x200) to component dimensions
      return {
        x: (point.x / 300) * width,
        y: (point.y / 200) * height,
      };
    },
    [width, height]
  );

  const currentCars = allLaps[currentLapIdx] ?? [];
  const trackInfo = getTrackById(raceId);
  const TrackComponent = trackInfo?.component ?? null;

  return (
    <div
      className="relative bg-gray-950 rounded-xl border border-gray-800 overflow-hidden"
      style={{ width, height }}
    >
      {/* Track SVG layer */}
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="absolute inset-0"
      >
        {/* Render track outline, capture path ref */}
        {TrackComponent && (
          <g transform={`scale(${width / 300}, ${height / 200})`}>
            <TrackComponent
              width={300}
              height={200}
              strokeColor="#374151"
              strokeWidth={3}
              showStartFinish
              animated={false}
              pathRef={trackRef}
            />
          </g>
        )}

        {/* Car dots */}
        {currentCars.map((car) => {
          const pos = getCarPosition(car.track_pct);
          const teamName = car.id.includes('norris') ? 'McLaren'
            : car.id.includes('verstappen') ? 'Red Bull'
            : car.id.includes('leclerc') || car.id.includes('hamilton') ? 'Ferrari'
            : 'Williams';
          const dotColor = TEAM_COLORS[teamName] ?? '#FFFFFF';

          return (
            <g key={car.id}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={6}
                fill={dotColor}
                stroke={COMPOUND_COLORS[car.compound] ?? '#FFF'}
                strokeWidth={1.5}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredCar(car)}
                onMouseLeave={() => setHoveredCar(null)}
              />
              <text
                x={pos.x + 8}
                y={pos.y + 4}
                fontSize={8}
                fill="#FFF"
                className="pointer-events-none select-none"
              >
                P{car.position}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-950/80">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            <p className="text-xs text-gray-400">Running simulation…</p>
          </div>
        </div>
      )}

      {/* Hover tooltip */}
      {hoveredCar && (
        <div className="absolute bottom-3 left-3 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-white">
          <div className="font-bold">{hoveredCar.id} · P{hoveredCar.position}</div>
          <div className="text-gray-400">
            {hoveredCar.compound} · {(hoveredCar.gap_ms / 1000).toFixed(3)}s gap
          </div>
        </div>
      )}

      {/* Summary badge */}
      {summary && (
        <div className="absolute top-3 right-3 bg-gray-900/90 border border-gray-700 rounded-lg px-3 py-2 text-xs">
          <div className="text-gray-400">P50 finish</div>
          <div className="text-white font-bold">P{summary.p50_finish}</div>
        </div>
      )}

      {/* Lap counter */}
      {allLaps.length > 0 && (
        <div className="absolute bottom-3 right-3 text-xs text-gray-500">
          Lap {currentLapIdx + 1}/{allLaps.length}
        </div>
      )}
    </div>
  );
};

export default RaceSimulator;
