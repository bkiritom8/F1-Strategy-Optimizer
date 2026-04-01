// frontend/components/SpeedLines.tsx
import { useEffect, useRef } from 'react';

interface Line {
  x: number;
  y: number;
  len: number;
  spd: number;
  w: number;
  alpha: number;
  red: boolean;
}

function mkLine(W: number, H: number): Line {
  return {
    x: Math.random() * W * 2 - W * 0.5,
    y: Math.random() * H,
    len: 60 + Math.random() * 260,
    spd: 18 + Math.random() * 38,
    w: 0.6 + Math.random() * 1.6,
    alpha: 0.12 + Math.random() * 0.38,
    red: Math.random() < 0.18,
  };
}

export function SpeedLines() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext('2d')!;
    let W = (cv.width = window.innerWidth);
    let H = (cv.height = window.innerHeight);

    const COUNT = 55;
    const lines: Line[] = Array.from({ length: COUNT }, () => mkLine(W, H));

    const onResize = () => {
      W = cv.width = window.innerWidth;
      H = cv.height = window.innerHeight;
    };
    window.addEventListener('resize', onResize);

    let last = performance.now();
    let rafId: number;

    function tick(now: number) {
      const dt = Math.min((now - last) / 16.67, 3);
      last = now;
      ctx.clearRect(0, 0, W, H);

      for (const l of lines) {
        l.x += l.spd * dt;

        if (l.x > W + l.len + 20) {
          l.x = -l.len - Math.random() * 200;
          l.y = Math.random() * H;
          l.len = 60 + Math.random() * 260;
          l.spd = 18 + Math.random() * 38;
          l.w = 0.6 + Math.random() * 1.6;
          l.alpha = 0.12 + Math.random() * 0.38;
          l.red = Math.random() < 0.18;
        }

        const ang = 0.04;
        const ex = l.x;
        const ey = l.y;
        const sx = l.x - l.len;
        const sy = l.y - l.len * ang;

        const g = ctx.createLinearGradient(sx, sy, ex, ey);
        if (l.red) {
          g.addColorStop(0, 'rgba(225,6,0,0)');
          g.addColorStop(0.6, `rgba(225,6,0,${l.alpha * 0.6})`);
          g.addColorStop(1, `rgba(225,6,0,${l.alpha})`);
        } else {
          g.addColorStop(0, 'rgba(255,255,255,0)');
          g.addColorStop(0.6, `rgba(220,235,255,${l.alpha * 0.6})`);
          g.addColorStop(1, `rgba(240,248,255,${l.alpha})`);
        }

        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
        ctx.strokeStyle = g;
        ctx.lineWidth = l.w;
        ctx.lineCap = 'round';
        ctx.stroke();
      }

      rafId = requestAnimationFrame(tick);
    }

    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1,
        pointerEvents: 'none',
      }}
    />
  );
}
