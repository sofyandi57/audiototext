"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from "react";

export interface PlayerHandle {
  seek: (seconds: number, play?: boolean) => void;
  audio: HTMLAudioElement | null;
}

const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2];

/** Sticky native <audio> player (native controls work best on Android). */
export const Player = forwardRef<
  PlayerHandle,
  {
    src: string | null;
    title?: ReactNode;
    onTime?: (t: number) => void;
    onEnded?: () => void;
    initialTime?: number;
    autoPlay?: boolean;
    extra?: ReactNode;
  }
>(function Player({ src, title, onTime, onEnded, initialTime, autoPlay, extra }, ref) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [rate, setRate] = useState(1);
  const pendingSeek = useRef<number | null>(initialTime ?? null);

  useImperativeHandle(ref, () => ({
    audio: audioRef.current,
    seek(seconds: number, play = true) {
      const a = audioRef.current;
      if (!a) return;
      if (a.readyState >= 1) a.currentTime = seconds;
      else pendingSeek.current = seconds;
      if (play) a.play().catch(() => undefined);
    },
  }));

  useEffect(() => {
    document.body.classList.toggle("has-player", !!src);
    return () => document.body.classList.remove("has-player");
  }, [src]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
  }, [rate, src]);

  useEffect(() => {
    pendingSeek.current = initialTime ?? null;
  }, [src, initialTime]);

  if (!src) return null;
  return (
    <div className="player" data-testid="player">
      <div className="player-inner">
        <div className="row between">
          <div className="player-title">{title}</div>
          <label className="row small">
            <span className="muted">Kecepatan</span>
            <select
              aria-label="Kecepatan putar"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              style={{ width: "auto", minHeight: 36, padding: "2px 6px" }}
            >
              {RATES.map((r) => (
                <option key={r} value={r}>
                  {r}×
                </option>
              ))}
            </select>
          </label>
        </div>
        <audio
          ref={audioRef}
          src={src}
          controls
          preload="metadata"
          autoPlay={autoPlay}
          onLoadedMetadata={(e) => {
            const a = e.currentTarget;
            a.playbackRate = rate;
            if (pendingSeek.current != null) {
              a.currentTime = Math.min(pendingSeek.current, a.duration || pendingSeek.current);
              pendingSeek.current = null;
            }
          }}
          onTimeUpdate={(e) => onTime?.(e.currentTarget.currentTime)}
          onEnded={onEnded}
        />
        {extra}
      </div>
    </div>
  );
});
