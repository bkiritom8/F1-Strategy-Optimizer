/**
 * @file TrackExplorer.tsx
 * @description Dedicated view for exploring all F1 circuits available in the platform.
 */

import React, { useEffect, useState } from 'react';
import { TrackGallery } from '../components/tracks/TrackGallery';
import { TrackDetailCard } from '../components/tracks/TrackDetailCard';
import { TrackInfo } from '../components/tracks/TrackMaps';
import { useAppStore } from '../store/useAppStore';

const TrackExplorer: React.FC = () => {
    const { setBackgroundCircuitId } = useAppStore();
    const [selectedTrack, setSelectedTrack] = useState<TrackInfo | null>(null);

    useEffect(() => {
        if (!selectedTrack) return;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = '';
        };
    }, [selectedTrack]);

    const handleTrackSelect = (track: TrackInfo) => {
        setSelectedTrack(track);
        setBackgroundCircuitId(track.id);
    };

    return (
        <div className="flex h-full overflow-hidden relative">
            {/* Left Pane: Track Gallery */}
            <div className={`flex-1 p-2 md:p-4 overflow-y-auto ${selectedTrack ? 'hidden xl:block xl:w-2/3' : 'w-full'} transition-all duration-300`}>
                <div className="mb-2 md:mb-4 border-b pb-2" style={{ borderColor: 'var(--border-color)' }}>
                    <h1 className="text-4xl font-display font-bold tracking-tight uppercase italic text-white">
                        Circuit Directory
                    </h1>
                    <p className="text-sm font-bold text-gray-400 uppercase tracking-widest mt-2">
                        Explore {selectedTrack ? 'selected circuit' : 'all available tracks'}
                    </p>
                </div>

                <TrackGallery
                    columns={selectedTrack ? 2 : 3}
                    selectedTrackId={selectedTrack?.id}
                    onTrackSelect={handleTrackSelect}
                />
            </div>

            {/* Mobile: open selected circuit as a viewport-anchored overlay */}
            {selectedTrack && (
                <div className="fixed inset-0 z-50 xl:hidden bg-black/70 backdrop-blur-md p-3 sm:p-4 overflow-y-auto">
                    <div className="min-h-full flex items-start justify-center">
                        <div className="w-full max-w-2xl">
                            <TrackDetailCard
                                trackId={selectedTrack.id}
                                onClose={() => setSelectedTrack(null)}
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Desktop: keep side detail pane */}
            {selectedTrack && (
                <div className="hidden xl:block xl:w-1/3 border-l overflow-y-auto p-4 md:p-6 bg-white/50 xl:dark:bg-black/20 backdrop-blur-xl transition-all duration-300" style={{ borderColor: 'var(--border-color)' }}>
                    <div className="sticky top-0">
                        <TrackDetailCard
                            trackId={selectedTrack.id}
                            onClose={() => setSelectedTrack(null)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default TrackExplorer;
