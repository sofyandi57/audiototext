"use client";

import { useEffect, useState } from "react";

/**
 * Preview using the device's own speech synthesis. This produces NO file —
 * it is only for checking the corrected text quickly before generating audio
 * on the server.
 */
export function BrowserSpeech({ text, rate = 1 }: { text: string; rate?: number }) {
  const [supported, setSupported] = useState(false);
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    setSupported(true);
    const pick = () => {
      const voices = window.speechSynthesis.getVoices();
      setVoice(voices.find((v) => v.lang?.toLowerCase().startsWith("id")) || null);
    };
    pick();
    window.speechSynthesis.addEventListener?.("voiceschanged", pick);
    return () => {
      window.speechSynthesis.removeEventListener?.("voiceschanged", pick);
      window.speechSynthesis.cancel();
    };
  }, []);

  if (!supported) return <p className="muted small">Pratinjau suara perangkat tidak didukung browser ini.</p>;

  const speak = () => {
    window.speechSynthesis.cancel();
    // Speak a bounded excerpt; long utterances are cut off on some Android builds.
    const u = new SpeechSynthesisUtterance(text.slice(0, 1500));
    u.lang = "id-ID";
    if (voice) u.voice = voice;
    u.rate = rate;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(u);
  };

  return (
    <div className="row">
      {speaking ? (
        <button className="btn btn-small" onClick={() => { window.speechSynthesis.cancel(); setSpeaking(false); }}>
          Hentikan pratinjau
        </button>
      ) : (
        <button className="btn btn-small" onClick={speak} disabled={!text.trim()}>
          Pratinjau suara perangkat
        </button>
      )}
      <span className="muted small">
        Hanya pratinjau, tidak menghasilkan file.{!voice && " Perangkat ini tidak memiliki suara Indonesia; lafal bisa keliru."}
      </span>
    </div>
  );
}
