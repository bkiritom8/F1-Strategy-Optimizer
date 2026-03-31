/**
 * @file TrackExplorer.tsx
 * @description Dedicated view for exploring all F1 circuits available in the platform.
 */

import React, { useState } from 'react';
import { TrackGallery } from '../components/tracks/TrackGallery';
import { TrackDetailCard } from '../components/tracks/TrackDetailCard';
import { TrackInfo } from '../components/tracks/TrackMaps';

interface TrackExplorerProps {
    theme?: 'dark' | 'light';
}

const TrackExplorer: React.FC<TrackExplorerProps> = ({ theme = 'dark' }) => {
    const [selectedTrack, setSelectedTrack] = useState<TrackInfo | null>(null);

    return (
        <div className="flex h-full overflow-hidden relative">
            {/* Left Pane: Track Gallery */}
            <div className={`flex-1 p-4 md:p-6 overflow-y-auto ${selectedTrack ? 'hidden xl:block xl:w-2/3' : 'w-full'} transition-all duration-300`}>
                <div className="mb-4 md:mb-6 border-b pb-4" style={{ borderColor: 'var(--border-color)' }}>
                    <h1 className="text-3xl md:text-4xl font-display font-black tracking-tighter uppercase italic text-gray-900 dark:text-white">
                        Circuit Directory
                    </h1>
                    <p className="text-sm font-bold text-gray-400 uppercase tracking-widest mt-2">
                        Explore {selectedTrack ? 'selected circuit' : 'all available tracks'}
                    </p>
                </div>

                <TrackGallery
                    theme={theme}
                    columns={selectedTrack ? 2 : 3}
                    selectedTrackId={selectedTrack?.id}
                    onTrackSelect={setSelectedTrack}
                />
            </div>

            {/* Right Pane: Track Details (Slide In) */}
            {selectedTrack && (
                <div className="absolute inset-0 xl:static xl:w-1/3 border-l overflow-y-auto p-4 md:p-6 bg-white/95 dark:bg-black/80 xl:bg-white/50 xl:dark:bg-black/20 backdrop-blur-xl z-20 xl:z-auto transition-all duration-300" style={{ borderColor: 'var(--border-color)' }}>
                    <div className="sticky top-0">
                        <TrackDetailCard
                            trackId={selectedTrack.id}
                            theme={theme}
                            onClose={() => setSelectedTrack(null)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default TrackExplorer;
