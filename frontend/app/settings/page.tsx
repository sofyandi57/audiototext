"use client";

import { useState } from "react";
import { api, ApiError, Capabilities, EngineInfo } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

export default function SettingsPage() {
  const auth = useResource(() => api<{ required: boolean; authenticated: boolean }>("/api/auth"), []);
  const caps = useResource(() => api<Capabilities>("/api/capabilities"), [auth.data?.authenticated]);
  const [token, setToken] = useState("");
  const [err, setErr] = useState<string | null>(null);

  return (
    <>
      <h1>Settings</h1>
      {auth.data?.required && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Akses</h2>
          {auth.data.authenticated ? (
            <div className="row between">
              <span className="badge badge-good">Sudah masuk</span>
              <button className="btn btn-small" onClick={async () => { await api("/api/auth", { method: "DELETE" }); auth.refresh(); }}>
                Keluar
              </button>
            </div>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setErr(null);
                try {
                  await api("/api/auth", { method: "POST", json: { token } });
                  setToken("");
                  auth.refresh();
                } catch (e2) {
                  setErr(e2 instanceof ApiError ? e2.message : String(e2));
                }
              }}
            >
              <label className="field">
                <span className="field-label">Token akses</span>
                <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="current-password" />
              </label>
              {err && <p className="error-text">{err}</p>}
              <button className="btn btn-primary">Masuk</button>
            </form>
          )}
        </section>
      )}

      <h2>Kemampuan server</h2>
      <p className="muted small">Pengaturan diatur lewat variabel lingkungan server (lihat .env.example). Halaman ini hanya menampilkan statusnya.</p>
      <ErrorBox error={caps.error} onRetry={caps.refresh} />
      {caps.loading && !caps.data && <Loading />}
      {caps.data && (
        <div data-testid="capabilities">
          <Engine title="Transkripsi (ASR)" e={caps.data.asr} />
          <Engine title="Diarisasi pembicara" e={caps.data.diarization} />
          <Engine title="Analisis rapat" e={caps.data.intelligence} />
          {caps.data.tts.map((t) => (
            <Engine key={t.name} title={`Suara (TTS): ${t.name}`} e={t} />
          ))}
          <Engine title="Suara perangkat (browser)" e={{ name: "speechSynthesis", available: true, reason: null, notes: "Hanya pratinjau di perangkat; tidak menghasilkan file unduhan." }} />
          <Engine title="OCR" e={{ name: "tesseract", available: caps.data.ocr.available, reason: caps.data.ocr.available ? null : "Tesseract atau data bahasa belum terpasang.", notes: caps.data.ocr.languages ? `Bahasa: ${caps.data.ocr.languages}` : undefined }} />
          <section className="card">
            <h3 style={{ marginTop: 0 }}>Batas & retensi</h3>
            <dl className="kv small">
              <dt>PDF</dt><dd>{caps.data.limits.max_pdf_mb} MB, {caps.data.limits.max_pdf_pages} halaman</dd>
              <dt>Audio/video</dt><dd>{caps.data.limits.max_media_mb} MB, {caps.data.limits.max_media_minutes} menit</dd>
              <dt>Retensi</dt><dd>{caps.data.retention_days > 0 ? `File dihapus otomatis setelah ${caps.data.retention_days} hari` : "Tidak ada penghapusan otomatis"}</dd>
              <dt>FFmpeg</dt><dd>{caps.data.ffmpeg ? "terpasang" : "tidak ada"}</dd>
            </dl>
          </section>
        </div>
      )}
    </>
  );
}

function Engine({ title, e }: { title: string; e: EngineInfo }) {
  return (
    <section className="card">
      <div className="row between">
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span className={`badge ${e.available ? "badge-good" : "badge-bad"}`}>{e.available ? "tersedia" : "tidak tersedia"}</span>
      </div>
      <dl className="kv small" style={{ marginTop: 6 }}>
        <dt>Mesin</dt>
        <dd>{e.name}{e.model ? ` (${e.model})` : ""}</dd>
        {e.reason && (<><dt>Alasan</dt><dd>{e.reason}</dd></>)}
        {e.license && (<><dt>Lisensi</dt><dd>{e.license}</dd></>)}
        {e.notes && (<><dt>Catatan</dt><dd>{e.notes}</dd></>)}
      </dl>
    </section>
  );
}
