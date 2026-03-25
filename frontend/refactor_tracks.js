const fs = require('fs');
const path = './components/tracks/TrackMaps.tsx';
let content = fs.readFileSync(path, 'utf8');

// Add 'animated?: boolean;' to TrackProps
content = content.replace(
  'showDRS?: boolean;\n  className?: string;',
  'showDRS?: boolean;\n  className?: string;\n  animated?: boolean;'
);

// Add 'animated: false,' to defaultProps
content = content.replace(
  "showDRS: false,\n  className: '',",
  "showDRS: false,\n  className: '',\n  animated: false,"
);

// Add import motion
content = content.replace(
  "import React from 'react';",
  "import React from 'react';\nimport { motion } from 'framer-motion';"
);

// Add AnimatedPath component before BahrainTrack
const animatedPathCode = `
const AnimatedPath: React.FC<{
  d: string;
  strokeColor?: string;
  strokeWidth?: number;
  fillColor?: string;
  animated?: boolean;
}> = ({ d, strokeColor, strokeWidth, fillColor, animated }) => {
  return (
    <>
      <path
        d={d}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill={fillColor}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {animated && (
        <motion.path
          d={d}
          stroke="#E10600"
          strokeWidth={(strokeWidth || 3) + 2}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0, pathOffset: 0 }}
          animate={{ pathOffset: 1 }}
          transition={{ duration: 6, ease: "linear", repeat: Infinity }}
          style={{ pathLength: 0.05, filter: "drop-shadow(0 0 6px #E10600)" }}
        />
      )}
    </>
  );
};
`;

content = content.replace(
  '// ============================================\n// BAHRAIN',
  animatedPathCode + '\n// ============================================\n// BAHRAIN'
);

// Add `animated` to the destructuring
content = content.replace(
  /const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className } = { \.\.\.defaultProps, \.\.\.props };/g,
  'const { width, height, strokeColor, strokeWidth, fillColor, showStartFinish, className, animated } = { ...defaultProps, ...props };'
);

// Replace path blocks
const pathRegex = /<path\s+d="([^"]+)"\s+stroke=\{strokeColor\}\s+strokeWidth=\{strokeWidth\}\s+fill=\{fillColor\}\s+strokeLinecap="round"\s+strokeLinejoin="round"\s+\/>/g;

content = content.replace(pathRegex, (match, dValue) => {
  return `<AnimatedPath d="${dValue}" strokeColor={strokeColor} strokeWidth={strokeWidth} fillColor={fillColor} animated={animated} />`;
});

fs.writeFileSync(path, content, 'utf8');
console.log("Refactored TrackMaps.tsx");
