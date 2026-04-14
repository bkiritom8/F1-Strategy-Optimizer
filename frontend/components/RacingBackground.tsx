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
    
    const baseSpeed = isChat ? 1.2 : isSim ? 2.8 : isProfile ? 3.4 : isCommand ? 6.4 : 4.2;
    const particleOpacity = isChat ? 0.025 : 0.045;
    
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
      speed: (baseSpeed * 1.7) + Math.random() * (baseSpeed * 0.9),
      color,
      width: 160,
      height: 22,
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
          ctx.lineWidth = 5;
          ctx.globalAlpha = theme === 'dark' ? 0.1 : 0.12;
            ctx.moveTo(car.trail[0].x, car.trail[0].y + car.height/2);
            for(let i=1; i < car.trail.length; i++) {
                ctx.lineTo(car.trail[i].x, car.trail[i].y + car.height/2);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        }

        const centerY = car.y + car.height / 2;
        const wheelYTop = car.y - 6;
        const wheelYBot = car.y + car.height + 6;

        // Main chassis
        ctx.fillStyle = car.color;
        ctx.beginPath();
        ctx.roundRect(car.x + 18, car.y + 2, car.width - 38, car.height - 4, 4);
        ctx.fill();

        // Nose cone
        ctx.beginPath();
        ctx.moveTo(car.x + 18, centerY - 4);
        ctx.lineTo(car.x - 10, centerY);
        ctx.lineTo(car.x + 18, centerY + 4);
        ctx.closePath();
        ctx.fill();

        // Rear body block
        ctx.fillRect(car.x + car.width - 26, car.y + 1, 20, car.height - 2);

        // Front and rear wings
        ctx.fillRect(car.x - 16, centerY - 1.5, 14, 3);
        ctx.fillRect(car.x + car.width - 6, car.y - 4, 12, 2.5);
        ctx.fillRect(car.x + car.width - 6, car.y + car.height + 1.5, 12, 2.5);

        // Specific mechanical colors for light mode
        const detailColor = theme === 'dark' ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.15)';
        const cockpitColor = theme === 'dark' ? 'rgba(0,0,0,0.7)' : 'rgba(0,0,0,0.8)';

        ctx.fillStyle = detailColor;
        ctx.fillRect(car.x + 36, car.y + 3, 16, car.height - 6);
        ctx.fillRect(car.x + 76, car.y + 3, 16, car.height - 6);

        ctx.fillStyle = cockpitColor;
        ctx.beginPath();
        ctx.ellipse(car.x + car.width * 0.48, centerY, 9, 5, 0, 0, Math.PI * 2);
        ctx.fill();

        // Wheels
        ctx.fillStyle = '#0b0b0b';
        ctx.fillRect(car.x + 18, wheelYTop, 8, 6);
        ctx.fillRect(car.x + 18, wheelYBot - 6, 8, 6);
        ctx.fillRect(car.x + car.width - 30, wheelYTop, 8, 6);
        ctx.fillRect(car.x + car.width - 30, wheelYBot - 6, 8, 6);

        car.x += car.speed;
        car.trail.push({x: car.x, y: car.y});
        if (car.trail.length > 50) car.trail.shift();

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
      style={{ opacity: theme === 'dark' ? 0.24 : 0.32 }}
    />
  );
};

export default RacingBackground;