/**
 * Track Components Index
 * Export all track-related components for Apex Intelligence
 */

// Individual Track SVG Components
export {
  BahrainTrack,
  JeddahTrack,
  MelbourneTrack,
  SuzukaTrack,
  ShanghaiTrack,
  MiamiTrack,
  ImolaTrack,
  MonacoTrack,
  MontrealTrack,
  BarcelonaTrack,
  SpielbergTrack,
  SilverstoneTrack,
  BudapestTrack,
  SpaTrack,
  ZandvoortTrack,
  MonzaTrack,
  SingaporeTrack,
  COTATrack,
  MexicoTrack,
  InterlagosTrack,
  VegasTrack,
  LusailTrack,
  YasMarinaTrack,
  MadridTrack,
  BhujTrack,
  ArgentinaTrack,
  
  // Registry & Helpers
  TRACK_REGISTRY,
  getTrackById,
  TrackDisplay,
  
  // Types
  type TrackInfo,
} from './TrackMaps';

// Gallery Component (shows all tracks in a grid)
export { TrackGallery } from './TrackGallery';

// Detail Card Component (detailed view of single track)
export { TrackDetailCard } from './TrackDetailCard';

// Default export
export { default } from './TrackMaps';
