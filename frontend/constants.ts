
/**
 * Application Constants
 * Defines the visual theme, team identities, and F1 glossary for the Apex Intelligence platform.
 */

export const APP_NAME = "Apex Intelligence";

export const COLORS = {
  dark: {
    bg: '#0F0F0F',
    secondary: '#1A1A1A',
    tertiary: '#252525',
    text: '#FFFFFF',
    textSecondary: '#6B7280',
    border: 'rgba(255, 255, 255, 0.05)',
    card: '#1A1A1A',
  },
  light: {
    bg: '#FCFBF7', // Warm Paper
    secondary: '#F0EFE9',
    tertiary: '#E5E4DE',
    text: '#1A1A1A',
    textSecondary: '#6B7280',
    border: 'rgba(0, 0, 0, 0.05)',
    card: '#FFFFFF',
  },
  accent: {
    red: '#E10600',
    green: '#00D2BE',
    yellow: '#FFF200',
    purple: '#9B59B6',
    blue: '#3498DB',
  },
  tires: {
    SOFT: '#FF3333',
    MEDIUM: '#FFD700',
    HARD: '#FFFFFF',
    INTERMEDIATE: '#39B54A',
    WET: '#3498DB',
  },
  modes: {
    PUSH: '#E10600',
    BALANCED: '#FFF200',
    CONSERVE: '#00D2BE',
  }
};

export const TEAM_COLORS: Record<string, string> = {
  'Red Bull': '#3671C6',
  'Mercedes': '#27F4D2',
  'Ferrari': '#E8002D',
  'McLaren': '#FF8000',
  'Aston Martin': '#229971',
  'Alpine': '#FF87BC',
  'Williams': '#64C4FF',
  'Haas': '#B6BABD',
  'RB': '#6692FF',
  'Sauber': '#52E252',
};

/**
 * F1 GLOSSARY
 * Beginner-friendly definitions for technical terms.
 */
export const F1_GLOSSARY: Record<string, string> = {
  ERS: "Energy Recovery System - harvester and storage of kinetic/heat energy to provide up to 160hp of electrical boost.",
  DRS: "Drag Reduction System - adjustable rear wing that opens to reduce air resistance and increase top speed by ~10-12 km/h.",
  'Tire Cliff': "The point where a tire's rubber has degraded so much that performance drops off immediately and drastically.",
  Undercut: "Pitting earlier than a rival to use the speed of fresh tires to jump ahead when the rival eventually pits.",
  'Brake Bias': "The distribution of braking force between the front and rear wheels, adjusted by the driver for different corners.",
  'Dirty Air': "Turbulent air left behind by a leading car, which reduces the aerodynamic downforce (grip) for the car following.",
  Delta: "The time difference between two cars, or between a driver's current lap and their best lap.",
  Apex: "The innermost point of the line taken through a curve, where the car is closest to the inside of the corner.",
  Stint: "The period between pit stops during which a driver is on track with a single set of tires.",
};

