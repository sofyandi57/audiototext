"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, Capabilities, DocumentDetail, fmtTime, Section } from "@/lib/api";
import { useLocalStorage, useResource } from "@/lib/hooks";
import { BrowserSpeech } from "@/components/BrowserSpeech";
import { Player, PlayerHandle } from "@/components/Player";
import { ConfirmButton, ErrorBox, JobPanel, Loading, StatusBadge } from "@/components/ui";

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <AudiobookView />
    </Suspense>
  );
}

type Tab = "text" | "preview" | "cleaning";

function audioBadge(s: Section) {
  if (!s.text.trim()) return <span className="badge badge-bad">kosong</span>;
  if (s.audio_status === "done" && s.audio_stale) return <span className="badge badge-busy">audio kedaluwarsa</span>;
  if (s.audio_status === "done") return <span className="badge badge-good">audio {fmtTime(s.audio_duration)}</span>;
  if (s.audio_status === "failed") return <span className="badge badge-bad">audio gagal</span>;
  return <span className="badge badge-muted">belum ada audio</span>;
}

function AudiobookView() {
  const id = useSearchParams().get("id") || "";
  const router = useRouter();
  const doc = useResource(
    () => api<DocumentDetail>(`/api/documents/${id}`),
    [id],
    (d) => !!d?.job && (d.job.status === "queued" || d.job.status === "running"),
    2000,
  );
  const caps = useResource(() => api<Capabilities>("/api/capabilities"), []);
  const [tab, setTab] = useState<Tab>("text");
  const [selected, setSelected] = useState<string | null>(null);
  const [progress, setProgress] = useLocalStorage<{ section?: string; time?: number }>(`ab:${id}`, {});
  const [autoNext, setAutoNext] = useState(true);
  const [playing, setPlaying] = useState<string | null>(null);
  const playerRef = useRef<PlayerHandle>(null);
  const d = doc.data;

  useEffect(() => {
    if (!d?.sections.length || selected) return;
    const resume = d.sections.find((s) => s.id === progress.section);
    setSelected((resume || d.sections[0]).id);
  }, [d, selected, progress.section]);

  const sections = d?.sections || [];
  const current = sections.find((s) => s.id === selected) || null;
  const playable = sections.filter((s) => s.audio_status === "done");
  const playingSection = sections.find((s) => s.id === playing) || null;

  if (!id) return <ErrorBox error="ID dokumen tidak ada di alamat." />;
  if (doc.loading && !d) return <Loading />;
  if (!d) return <ErrorBox error={doc.error} onRetry={doc.refresh} />;

  const busy = !!d.job && (d.job.status === "queued" || d.job.status === "running");
  const allAudio = sections.filter((s) => s.text.trim()).every((s) => s.audio_status === "done");
  const reviewPages = d.cleaning_report?.review_pages || [];

  const play = (s: Section, from = 0) => {
    setPlaying(s.id);
    setSelected(s.id);
    setProgress({ section: s.id, time: from });
    setTimeout(() => playerRef.current?.seek(from, true), 50);
  };

  return (
    <>
      <p className="small">
        <Link href="/audiobooks/">← PDF Audiobook</Link>
      </p>
      <div className="row between">
        <h1 data-testid="doc-title">{d.filename}</h1>
        <StatusBadge status={d.status} />
      </div>
      <p className="muted small">
        {d.page_count ? `${d.page_count} halaman · ` : ""}
        {sections.length} bagian · audio {d.with_audio}/{sections.length}
      </p>

      <ErrorBox error={doc.error} />
      {d.error && d.status !== "failed" && <div className="alert alert-error"><p>{d.error}</p></div>}
      {d.status === "failed" && (
        <div className="alert alert-error" role="alert" data-testid="doc-failed">
          <p>
            <strong>Pemrosesan gagal.</strong> {d.error}
          </p>
        </div>
      )}
      <JobPanel job={d.job} onChange={doc.refresh} />

      {(d.status === "uploaded" || d.status === "extracting") && (
        <p className="muted">Teks sedang diekstrak. Halaman ini diperbarui otomatis.</p>
      )}

      {reviewPages.length > 0 && (
        <div className="alert alert-warn" data-testid="review-pages">
          <p>
            <strong>{reviewPages.length} halaman perlu ditinjau</strong> (tidak dilewati diam-diam):
          </p>
          <ul className="small">
            {reviewPages.slice(0, 10).map((r) => (
              <li key={r.page}>
                Hlm {r.page}: {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.cleaning_report?.warning && <div className="alert alert-warn"><p>{d.cleaning_report.warning}</p></div>}

      {sections.length > 0 && (
        <>
          <VoiceSettings docId={id} caps={caps.data} current={current} busy={busy} onQueued={doc.refresh} />

          <div className="tabs" role="tablist">
            {([["text", "Bab & teks"], ["preview", "Pratinjau PDF"], ["cleaning", "Pembersihan"]] as [Tab, string][]).map(
              ([k, label]) => (
                <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
                  {label}
                </button>
              ),
            )}
          </div>

          {tab === "text" && (
            <div className="grid grid-2">
              <div className="card" style={{ padding: 0 }}>
                <ol className="list" aria-label="Daftar bab" data-testid="chapter-list">
                  {sections.map((s) => (
                    <li key={s.id} style={{ padding: 0 }}>
                      <button className="chapter" aria-current={s.id === selected} onClick={() => setSelected(s.id)}>
                        <span className="chapter-idx">{s.idx + 1}</span>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          <span className="item-title" style={{ paddingLeft: (s.level - 1) * 10 }}>
                            {s.title}
                          </span>
                          <span className="row small" style={{ marginTop: 2 }}>
                            {audioBadge(s)}
                            {s.needs_review ? <span className="badge badge-busy">perlu ditinjau</span> : null}
                            {s.edited ? <span className="badge badge-info">diedit</span> : null}
                            <span className="muted">
                              hlm {s.start_page}
                              {s.end_page && s.end_page !== s.start_page ? `–${s.end_page}` : ""}
                            </span>
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
              {current && (
                <SectionEditor
                  key={current.id}
                  docId={id}
                  section={current}
                  onSaved={doc.refresh}
                  onPlay={() => play(current)}
                />
              )}
            </div>
          )}

          {tab === "preview" && <PdfPreview doc={d} initialPage={current?.start_page || 1} />}
          {tab === "cleaning" && <CleaningReport doc={d} />}

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Unduh</h2>
            <div className="row">
              {allAudio && playable.length > 0 ? (
                <a className="btn btn-primary" href={`/api/documents/${id}/audiobook.mp3`} download data-testid="download-book">
                  Unduh audiobook lengkap (MP3)
                </a>
              ) : (
                <button className="btn" disabled>
                  Audiobook lengkap (tunggu semua bab selesai)
                </button>
              )}
              <a className="btn" href={`/api/documents/${id}/text.txt`} download>
                Teks (.txt)
              </a>
              <a className="btn" href={`/api/documents/${id}/file`} target="_blank" rel="noreferrer">
                PDF asli
              </a>
            </div>
            {progress.section && sections.find((s) => s.id === progress.section)?.audio_status === "done" && !playing && (
              <p className="small">
                <button className="linklike" onClick={() => play(sections.find((s) => s.id === progress.section)!, progress.time || 0)}>
                  Lanjutkan mendengarkan: {sections.find((s) => s.id === progress.section)?.title} ({fmtTime(progress.time)})
                </button>
              </p>
            )}
          </div>
        </>
      )}

      <div className="card">
        <ConfirmButton
          confirmText="Hapus dokumen ini beserta semua audio yang dihasilkan? Tindakan ini tidak bisa dibatalkan."
          onConfirm={async () => {
            await api(`/api/documents/${id}`, { method: "DELETE" });
            router.push("/audiobooks/");
          }}
        >
          Hapus dokumen & audio
        </ConfirmButton>
      </div>

      <Player
        ref={playerRef}
        src={playingSection ? `/api/documents/${id}/sections/${playingSection.id}/audio` : null}
        title={playingSection ? `${playingSection.idx + 1}. ${playingSection.title}` : ""}
        initialTime={playingSection && progress.section === playingSection.id ? progress.time : 0}
        onTime={(t) => {
          if (playingSection && Math.abs((progress.time || 0) - t) > 5) setProgress({ section: playingSection.id, time: t });
        }}
        onEnded={() => {
          if (!playingSection) return;
          const next = playable.find((s) => s.idx > playingSection.idx);
          if (autoNext && next) play(next);
          else setProgress({ section: playingSection.id, time: 0 });
        }}
        extra={
          <div className="row small">
            {playingSection && (
              <a href={`/api/documents/${id}/sections/${playingSection.id}/audio?download=1`}>Unduh bab ini</a>
            )}
            <label className="row">
              <input type="checkbox" checked={autoNext} onChange={(e) => setAutoNext(e.target.checked)} /> Lanjut otomatis
            </label>
          </div>
        }
      />
    </>
  );
}

function SectionEditor({ docId, section, onSaved, onPlay }: { docId: string; section: Section; onSaved: () => void; onPlay: () => void }) {
  const [title, setTitle] = useState(section.title);
  const [text, setText] = useState(section.text);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const dirty = title !== section.title || text !== section.text;

  const save = async (extra: Record<string, unknown> = {}) => {
    setSaving(true);
    setErr(null);
    try {
      await api(`/api/documents/${docId}/sections/${section.id}`, { method: "PATCH", json: { title, text, ...extra } });
      setMsg("Tersimpan.");
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" data-testid="section-editor">
      <label className="field">
        <span className="field-label">Judul bab</span>
        <input type="text" value={title} onChange={(e) => { setTitle(e.target.value); setMsg(null); }} />
      </label>
      <label className="field">
        <span className="field-label">Teks yang akan dibacakan ({text.length.toLocaleString("id-ID")} karakter)</span>
        <textarea value={text} onChange={(e) => { setText(e.target.value); setMsg(null); }} data-testid="section-text" />
      </label>
      {section.audio_error && <p className="error-text">{section.audio_error}</p>}
      {section.audio_stale && <p className="muted small">Teks berubah sejak audio dibuat. Buat ulang audio bab ini.</p>}
      {err && <p className="error-text">{err}</p>}
      <div className="row">
        <button className="btn btn-primary btn-small" disabled={!dirty || saving} onClick={() => save()}>
          {saving ? "Menyimpan…" : "Simpan koreksi"}
        </button>
        {section.needs_review ? (
          <button className="btn btn-small" disabled={saving} onClick={() => save({ needs_review: false })}>
            Tandai sudah ditinjau
          </button>
        ) : null}
        {section.audio_status === "done" && (
          <button className="btn btn-small" onClick={onPlay} data-testid="play-section">
            ▶ Putar audio
          </button>
        )}
        {msg && <span className="muted small">{msg}</span>}
      </div>
      <div style={{ marginTop: 10 }}>
        <BrowserSpeech text={text} />
      </div>
    </div>
  );
}

function VoiceSettings({ docId, caps, current, busy, onQueued }: {
  docId: string; caps: Capabilities | null; current: Section | null; busy: boolean; onQueued: () => void;
}) {
  const engines = caps?.tts || [];
  const [engine, setEngine] = useState<string>("");
  const [voice, setVoice] = useState<string>("");
  const [rate, setRate] = useState(160);
  const [err, setErr] = useState<string | null>(null);
  const info = useMemo(() => engines.find((e) => e.name === engine), [engines, engine]);

  useEffect(() => {
    if (!engine && caps) {
      const def = engines.find((e) => e.name === caps.tts_default && e.available) || engines.find((e) => e.available);
      if (def) {
        setEngine(def.name);
        setVoice(def.voices?.[0]?.id || "");
      }
    }
  }, [caps, engine, engines]);

  const generate = async (sectionIds?: string[]) => {
    setErr(null);
    try {
      await api(`/api/documents/${docId}/tts`, {
        method: "POST",
        json: { engine, voice: voice || null, rate, section_ids: sectionIds || null },
      });
      onQueued();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  };

  const none = caps && !engines.some((e) => e.available);
  return (
    <div className="card" data-testid="voice-settings">
      <h2 style={{ marginTop: 0 }}>Suara</h2>
      {none ? (
        <p className="error-text">Tidak ada mesin TTS server yang tersedia. Gunakan pratinjau suara perangkat untuk sementara.</p>
      ) : (
        <>
          <div className="grid grid-2">
            <label className="field">
              <span className="field-label">Mesin</span>
              <select value={engine} onChange={(e) => setEngine(e.target.value)}>
                {engines.map((e) => (
                  <option key={e.name} value={e.name} disabled={!e.available}>
                    {e.name}
                    {e.available ? "" : " (tidak tersedia)"}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Suara</span>
              <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                {(info?.voices || []).map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="field">
            <span className="field-label">Kecepatan: {rate} kata/menit</span>
            <input type="range" min={80} max={300} step={10} value={rate} onChange={(e) => setRate(Number(e.target.value))} />
          </label>
          {info?.notes && <p className="muted small">{info.notes}</p>}
          {err && <p className="error-text" role="alert">{err}</p>}
          <div className="row">
            <button className="btn btn-primary" disabled={busy || !engine} onClick={() => generate()} data-testid="generate-all">
              Buat audio semua bab
            </button>
            {current && (
              <button className="btn" disabled={busy || !engine || !current.text.trim()} onClick={() => generate([current.id])}>
                Buat audio bab ini
              </button>
            )}
          </div>
          <p className="muted small">Bab yang audionya sudah dibuat dari teks dan pengaturan yang sama tidak diproses ulang.</p>
        </>
      )}
    </div>
  );
}

function PdfPreview({ doc, initialPage }: { doc: DocumentDetail; initialPage: number }) {
  const [page, setPage] = useState(initialPage);
  const total = doc.page_count || 1;
  const meta = doc.pages.find((p) => p.page_no === page);
  return (
    <div className="card">
      <div className="row between">
        <button className="btn btn-small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          ‹ Sebelumnya
        </button>
        <span className="small">
          Hlm{" "}
          <input
            type="number"
            min={1}
            max={total}
            value={page}
            onChange={(e) => setPage(Math.min(total, Math.max(1, Number(e.target.value) || 1)))}
            style={{ width: 72, display: "inline-block" }}
            aria-label="Nomor halaman"
          />{" "}
          / {total}
        </span>
        <button className="btn btn-small" disabled={page >= total} onClick={() => setPage(page + 1)}>
          Berikutnya ›
        </button>
      </div>
      {meta && (
        <p className="muted small">
          Sumber teks: {meta.text_source === "ocr" ? "OCR" : meta.text_source === "text" ? "lapisan teks PDF" : "tidak ada"} ·{" "}
          {meta.char_count} karakter
          {meta.needs_review ? ` · perlu ditinjau: ${meta.review_reason}` : ""}
        </p>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="page-preview" src={`/api/documents/${doc.id}/pages/${page}/preview`} alt={`Halaman ${page}`} loading="lazy" />
    </div>
  );
}

function CleaningReport({ doc }: { doc: DocumentDetail }) {
  const r = doc.cleaning_report;
  if (!r) return <p className="muted">Belum ada laporan.</p>;
  const reasonLabel: Record<string, string> = { header: "Header berulang", footer: "Footer berulang", page_number: "Nomor halaman" };
  return (
    <div className="card" data-testid="cleaning-report">
      <dl className="kv">
        {Object.entries(r.summary).map(([k, v]) => (
          <FragmentKV key={k} k={reasonLabel[k] || k} v={`${v} baris dihapus`} />
        ))}
        <FragmentKV k="Pemenggalan kata diperbaiki" v={String(r.dehyphenated)} />
        <FragmentKV k="Paragraf disambung lintas halaman" v={String(r.merged_across_pages)} />
        <FragmentKV k="Struktur bab dari bookmark PDF" v={r.used_outline ? "ya" : "tidak (deteksi judul)"} />
        <FragmentKV k="Halaman OCR" v={r.ocr_pages.length ? r.ocr_pages.join(", ") : "-"} />
      </dl>
      {r.removed.length > 0 && (
        <>
          <h3>Baris yang dihapus</h3>
          <p className="muted small">Jika ada isi penting yang ikut terhapus, tambahkan kembali lewat editor teks.</p>
          <ul className="small">
            {r.removed.slice(0, 200).map((x, i) => (
              <li key={i}>
                Hlm {x.page} · {reasonLabel[x.reason] || x.reason}: “{x.text}”
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function FragmentKV({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
