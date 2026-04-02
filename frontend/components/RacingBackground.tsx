/**
 * @file RacingBackground.tsx
 * @description Renders a high-performance Canvas animation representing the flow of data
 * and motion in a racing environment. Car speeds are tuned for professional realism.
 */

import React, { useEffect, useRef } from 'react';

interface RacingBackgroundProps {
  /** The current active route/view identifier to adjust animation style */
  view: string;
  theme: 'dark' | 'light';
}

const RacingBackground: React.FC<RacingBackgroundProps> = ({ view, theme }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = window.innerWidth;
    let height = window.innerHeight;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
    };

    window.addEventListener('resize', resize);
    resize();

    const isChat = view === 'ai';
    const isProfile = view === 'profiles';
    const isSim = view === 'sim';
    const isCommand = view === 'command';
    
    const baseSpeed = isChat ? 0.6 : isSim ? 1.6 : isProfile ? 2.4 : isCommand ? 4.5 : 3.0;
    const particleOpacity = isChat ? 0.03 : 0.06;
    
    // Light mode car colors need to be slightly darker/more vibrant for contrast
    const carColors = theme === 'dark' 
      ? ['#E10600', '#3671C6', '#00D2BE', '#FF8000', '#FFFFFF']
      : ['#D10500', '#2B5BA5', '#00B0A0', '#E57300', '#1A1A1A'];
    
    const particleColor = theme === 'dark' ? '255, 255, 255' : '0, 0, 0';

    interface Particle {
      x: number; y: number; speed: number; length: number; opacity: number;
    }

    interface Car {
      x: number; y: number; speed: number; color: string; width: number; height: number;
      trail: {x: number, y: number}[];
    }

    const particles: Particle[] = Array.from({ length: isChat ? 25 : 80 }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      speed: (baseSpeed * 0.4) + Math.random() * baseSpeed,
      length: 80 + Math.random() * 150,
      opacity: particleOpacity + Math.random() * 0.05,
    }));

    const cars: Car[] = carColors.map((color, i) => ({
      x: -300 - (Math.random() * 5000),
      y: (height / carColors.length) * i + (Math.random() * 40),
      speed: (baseSpeed * 1.5) + Math.random() * baseSpeed,
      color,
      width: 140,
      height: 24,
      trail: []
    }));

    const animate = () => {
      // Background matches theme
      ctx.fillStyle = theme === 'dark' ? '#0F0F0F' : '#FCFBF7';
      ctx.fillRect(0, 0, width, height);

      ctx.lineWidth = 1;
      particles.forEach(p => {
        ctx.strokeStyle = `rgba(${particleColor}, ${p.opacity})`;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x + p.length, p.y);
        ctx.stroke();

        p.x += p.speed;
        if (p.x > width) {
          p.x = -p.length;
          p.y = Math.random() * height;
        }
      });

      cars.forEach(car => {
        if (car.trail.length > 2) {
            ctx.beginPath();
            ctx.strokeStyle = car.color;
            ctx.lineWidth = 6;
            ctx.globalAlpha = theme === 'dark' ? 0.08 : 0.15;
            ctx.moveTo(car.trail[0].x, car.trail[0].y + car.height/2);
            for(let i=1; i < car.trail.length; i++) {
                ctx.lineTo(car.trail[i].x, car.trail[i].y + car.height/2);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        }

        ctx.fillStyle = car.color;
        ctx.beginPath();
        ctx.roundRect(car.x, car.y, car.width, car.height, 6);
        ctx.fill();

        // Specific mechanical colors for light mode
        const detailColor = theme === 'dark' ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.1)';
        const cockpitColor = theme === 'dark' ? 'rgba(0,0,0,0.7)' : 'rgba(0,0,0,0.8)';

        ctx.fillStyle = detailColor;
        ctx.fillRect(car.x + car.width - 20, car.y - 8, 5, car.height + 16);
        ctx.fillRect(car.x, car.y - 8, 10, car.height + 16);

        ctx.fillStyle = cockpitColor;
        ctx.fillRect(car.x + car.width * 0.4, car.y + 5, car.width * 0.15, car.height - 10);

        car.x += car.speed;
        car.trail.push({x: car.x, y: car.y});
        if (car.trail.length > 60) car.trail.shift();

        if (car.x > width + 600) {
          car.x = -600 - (Math.random() * 4000);
          car.y = Math.random() * height;
          car.speed = (baseSpeed * 1.5) + Math.random() * baseSpeed;
          car.trail = [];
        }
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resize);
    };
  }, [view, theme]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0"
      style={{ opacity: theme === 'dark' ? 0.1 : 0.4 }}
    />
  );
};

export default RacingBackground;