import React, { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

interface AudioWaveformProps {
  audioUrl: string;
  height?: number;
  className?: string;
}

const AudioWaveform: React.FC<AudioWaveformProps> = ({
  audioUrl,
  height = 32,
  className = "",
}) => {
  const waveformRef = useRef<HTMLDivElement>(null);
  const wavesurfer = useRef<WaveSurfer | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!waveformRef.current) return;

    const ws = WaveSurfer.create({
      container: waveformRef.current,
      waveColor: "rgba(255, 255, 255, 0.6)",
      progressColor: "rgba(255, 255, 255, 0.9)",
      cursorColor: "transparent",
      barWidth: 2,
      barGap: 1,
      height,
      normalize: true,
      interact: false,
    });

    wavesurfer.current = ws;

    const handleReady = () => {
      setIsLoading(false);
      setError(false);
    };

    const handleError = (err: Error) => {
      if (err.name === "AbortError") {
        return;
      }
      console.error("WaveSurfer error:", err);
      setError(true);
      setIsLoading(false);
    };

    ws.on("ready", handleReady);
    ws.on("error", handleError);

    ws.load(audioUrl).catch(handleError);

    return () => {
      ws.un("ready", handleReady);
      ws.un("error", handleError);
      ws.destroy();
    };
  }, [audioUrl, height]);

  if (error) {
    return (
      <div
        className={`flex items-center justify-center ${className}`}
        style={{ height }}
      >
        <span className="text-xs text-foreground/60">Audio unavailable</span>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-foreground/60">Loading...</span>
        </div>
      )}
      <div
        ref={waveformRef}
        className={`w-full transition-opacity duration-200 ${isLoading ? "opacity-0" : "opacity-100"}`}
        style={{ height }}
      />
    </div>
  );
};

export default AudioWaveform;