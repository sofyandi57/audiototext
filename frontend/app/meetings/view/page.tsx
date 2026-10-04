"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useRef, useState } from "react";
import { api, ApiError, fmtTime, Insight, MeetingDetail, Segment } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { Player, PlayerHandle } from "@/components/Player";
import { ConfirmButton, Empty, ErrorBox, JobPanel, Loading, StatusBadge } from "@/components/ui";

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <MeetingView />
    </Suspense>
  );
}

type Tab = "summary" | "transcript" | "speakers" | "decisions" | "actions" | "risks";
const TABS: [Tab, string][] = [
  ["summary", "Ringkasan"],
  ["transcript", "Transkrip"],
  ["speakers", "Pembicara"],
  ["decisions", "Keputusan"],
  ["actions", "Tindak lanjut"],
  ["risks", "Risiko & pertanyaan"],
];

function isActive(j: { status: string } | null | undefined) {
  return !!j && (j.status === "queued" || j.status === "running");
}

function MeetingView() {
  const id = useSearchParams().get("id") || "";
  const router = useRouter();
  const m = useResource(
    () => api<MeetingDetail>(`/api/meetings/${id}`),
    [id],
    (d) => !!d && (isActive(d.jobs.meeting_transcribe) || isActive(d.jobs.meeting_analyze)),
    2500,
  );
  const [tab, setTab] = useState<Tab>("summary");
  const [now, setNow] = useState(0);
  const [focusSeg, setFocusSeg] = useState<string | null>(null);
  const playerRef = useRef<PlayerHandle>(null);
  const d = m.data;

  const seek = (t: number, segId?: string) => {
    playerRef.current?.seek(t, true);
    if (segId) setFocusSeg(segId);
  };
  const goToSegment = (segId: string, t: number) => {
    setTab("transcript");
    seek(t, segId);
    setTimeout(() => document.getElementById(`seg-${segId}`)?.scrollIntoView({ block: "center" }), 60);
  };

  if (!id) return <ErrorBox error="ID rapat tidak ada di alamat." />;
  if (m.loading && !d) return <Loading />;
  if (!d) return <ErrorBox error={m.error} onRetry={m.refresh} />;

  const analyzeJob = d.jobs.meeting_analyze;
  const byKind = (k: Insight["kind"]) => d.insights.filter((i) => i.kind === k);

  return (
    <>
      <p className="small">
        <Link href="/meetings/">← Rapat</Link>
      </p>
      <TitleEditor meeting={d} onSaved={m.refresh} />
      <p className="muted small">
        {d.filename} · durasi {fmtTime(d.duration)} · {d.segments.length} segmen
        {d.asr_model ? ` · model ${d.asr_model}` : ""}
      </p>
      <ErrorBox error={m.error} />
      {d.status === "failed" && (
        <div className="alert alert-error" role="alert" data-testid="meeting-failed">
          <p>
            <strong>Transkripsi gagal.</strong> {d.error}
          </p>
          {d.has_audio && <p className="small">Audio tetap bisa diputar. Gunakan “Ulangi” setelah masalah diperbaiki.</p>}
        </div>
      )}
      <JobPanel job={d.jobs.meeting_transcribe} onChange={m.refresh} />
      {analyzeJob && analyzeJob.status !== "succeeded" && <JobPanel job={analyzeJob} onChange={m.refresh} compact />}

      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {label}
            {k === "decisions" && byKind("decision").length ? ` (${byKind("decision").length})` : ""}
            {k === "actions" && byKind("action").length ? ` (${byKind("action").length})` : ""}
          </button>
        ))}
      </div>

      {tab === "summary" && (
        <InsightList
          items={byKind("summary")}
          analyzeJob={analyzeJob}
          hasTranscript={d.segments.length > 0}
          empty="Belum ada ringkasan."
          note="Ringkasan ekstraktif: kalimat penting dikutip apa adanya dari transkrip, bukan dikarang ulang."
          onJump={goToSegment}
        />
      )}
      {tab === "transcript" && (
        <Transcript meeting={d} now={now} focus={focusSeg} onSeek={seek} onChanged={m.refresh} />
      )}
      {tab === "speakers" && <Speakers meeting={d} onChanged={m.refresh} />}
      {tab === "decisions" && (
        <InsightList items={byKind("decision")} analyzeJob={analyzeJob} hasTranscript={d.segments.length > 0}
          empty="Tidak ada keputusan yang terdeteksi secara eksplisit." onJump={goToSegment} />
      )}
      {tab === "actions" && (
        <InsightList items={byKind("action")} analyzeJob={analyzeJob} hasTranscript={d.segments.length > 0}
          empty="Tidak ada tindak lanjut yang terdeteksi." onJump={goToSegment} />
      )}
      {tab === "risks" && (
        <>
          <h2>Risiko</h2>
          <InsightList items={byKind("risk")} analyzeJob={analyzeJob} hasTranscript={d.segments.length > 0}
            empty="Tidak ada risiko yang terdeteksi." onJump={goToSegment} />
          <h2>Pertanyaan terbuka</h2>
          <InsightList items={byKind("question")} analyzeJob={analyzeJob} hasTranscript={d.segments.length > 0}
            empty="Tidak ada pertanyaan terbuka yang terdeteksi." onJump={goToSegment} />
        </>
      )}

      <div className="card">
        <div className="row">
          <a className="btn btn-small" href={`/api/meetings/${id}/export.txt`} download>
            Ekspor TXT
          </a>
          <a className="btn btn-small" href={`/api/meetings/${id}/export.md`} download>
            Ekspor Markdown
          </a>
          <button
            className="btn btn-small"
            disabled={!d.segments.length || isActive(analyzeJob)}
            onClick={async () => {
              await api(`/api/meetings/${id}/analyze`, { method: "POST" });
              m.refresh();
            }}
          >
            Analisis ulang
          </button>
          <ConfirmButton
            confirmText="Hapus rapat ini beserta rekaman dan transkripnya? Tindakan ini tidak bisa dibatalkan."
            onConfirm={async () => {
              await api(`/api/meetings/${id}`, { method: "DELETE" });
              router.push("/meetings/");
            }}
          >
            Hapus
          </ConfirmButton>
        </div>
        <p className="muted small">Analisis ulang setelah mengoreksi transkrip atau nama pembicara.</p>
      </div>

      <Player ref={playerRef} src={d.has_audio ? `/api/meetings/${id}/audio` : null} title={d.title || d.filename} onTime={setNow} />
    </>
  );
}

function TitleEditor({ meeting, onSaved }: { meeting: MeetingDetail; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(meeting.title || "");
  if (!editing)
    return (
      <div className="row between">
        <h1 data-testid="meeting-title">{meeting.title || meeting.filename}</h1>
        <div className="row">
          <StatusBadge status={meeting.status} />
          <button className="linklike small" onClick={() => setEditing(true)}>
            Ubah judul
          </button>
        </div>
      </div>
    );
  return (
    <form
      className="row"
      onSubmit={async (e) => {
        e.preventDefault();
        await api(`/api/meetings/${meeting.id}`, { method: "PATCH", json: { title } });
        setEditing(false);
        onSaved();
      }}
    >
      <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label="Judul rapat" />
      <button className="btn btn-small btn-primary" disabled={!title.trim()}>
        Simpan
      </button>
      <button type="button" className="btn btn-small" onClick={() => setEditing(false)}>
        Batal
      </button>
    </form>
  );
}

function InsightList({ items, analyzeJob, hasTranscript, empty, note, onJump }: {
  items: Insight[]; analyzeJob: MeetingDetail["jobs"]["meeting_analyze"]; hasTranscript: boolean;
  empty: string; note?: string; onJump: (segId: string, t: number) => void;
}) {
  if (!hasTranscript) return <Empty title="Belum ada transkrip">Analisis berjalan setelah transkripsi selesai.</Empty>;
  if (analyzeJob?.status === "failed")
    return (
      <div className="alert alert-warn" data-testid="analysis-unavailable">
        <p><strong>Analisis tidak tersedia.</strong> {analyzeJob.error}</p>
        <p className="small">Transkrip tetap dapat dibaca, diedit, dan diekspor.</p>
      </div>
    );
  if (isActive(analyzeJob)) return <Loading label="Menganalisis transkrip…" />;
  return (
    <>
      {note && <p className="muted small">{note}</p>}
      {!items.length ? (
        <Empty title={empty} />
      ) : (
        <ul className="list" data-testid="insights">
          {items.map((it) => (
            <li key={it.id}>
              <p className="segment-text" style={{ marginTop: 0 }}>{it.text}</p>
              {it.kind === "action" && (
                <p className="small row">
                  <span>
                    PIC:{" "}
                    {it.owner_confirmed && it.owner ? <strong>{it.owner}</strong> : <span className="badge badge-busy">belum dikonfirmasi</span>}
                  </span>
                  <span>
                    Tenggat:{" "}
                    {it.deadline_confirmed && it.deadline ? <strong>{it.deadline}</strong> : <span className="badge badge-busy">belum dikonfirmasi</span>}
                  </span>
                </p>
              )}
              <button className="linklike ts" onClick={() => onJump(it.segment_ids[0], it.start)}>
                ▶ {fmtTime(it.start)} · lihat di transkrip
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Transcript({ meeting, now, focus, onSeek, onChanged }: {
  meeting: MeetingDetail; now: number; focus: string | null; onSeek: (t: number, segId?: string) => void; onChanged: () => void;
}) {
  const [query, setQuery] = useState("");
  const speakers = useMemo(
    () => Array.from(new Set(meeting.segments.map((s) => s.speaker).filter(Boolean))) as string[],
    [meeting.segments],
  );
  if (!meeting.segments.length)
    return <Empty title="Transkrip belum tersedia">{meeting.status === "failed" ? "Transkripsi gagal — lihat pesan di atas." : "Menunggu transkripsi selesai."}</Empty>;
  const q = query.trim().toLowerCase();
  const rows = q ? meeting.segments.filter((s) => s.text.toLowerCase().includes(q) || (s.speaker || "").toLowerCase().includes(q)) : meeting.segments;
  return (
    <>
      <input type="text" placeholder="Cari di transkrip…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Cari di transkrip" />
      <datalist id="speaker-names">
        {speakers.map((s) => <option key={s} value={s} />)}
      </datalist>
      <div data-testid="transcript">
        {rows.map((s) => (
          <SegmentRow key={s.id} seg={s} meetingId={meeting.id} active={(now >= s.start && now < s.end) || focus === s.id} onSeek={onSeek} onChanged={onChanged} />
        ))}
      </div>
    </>
  );
}

function SegmentRow({ seg, meetingId, active, onSeek, onChanged }: {
  seg: Segment; meetingId: string; active: boolean; onSeek: (t: number, id?: string) => void; onChanged: () => void;
}) {
  const [mode, setMode] = useState<"view" | "text" | "speaker">("view");
  const [text, setText] = useState(seg.text);
  const [speaker, setSpeaker] = useState(seg.speaker || "");
  const [err, setErr] = useState<string | null>(null);

  const save = async (body: Record<string, string>) => {
    setErr(null);
    try {
      await api(`/api/meetings/${meetingId}/segments/${seg.id}`, { method: "PATCH", json: body });
      setMode("view");
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <div id={`seg-${seg.id}`} className={`segment ${active ? "active" : ""}`} data-testid="segment">
      <div className="row">
        <button className="linklike ts" onClick={() => onSeek(seg.start, seg.id)} aria-label={`Putar dari ${fmtTime(seg.start)}`}>
          {fmtTime(seg.start)}
        </button>
        {mode === "speaker" ? (
          <form className="row" onSubmit={(e) => { e.preventDefault(); save({ speaker }); }}>
            <input type="text" list="speaker-names" value={speaker} onChange={(e) => setSpeaker(e.target.value)} maxLength={60} placeholder="Nama pembicara" aria-label="Nama pembicara" style={{ width: 160 }} />
            <button className="btn btn-small btn-primary">Simpan</button>
            <button type="button" className="btn btn-small" onClick={() => setMode("view")}>Batal</button>
          </form>
        ) : (
          <button className="linklike speaker" onClick={() => setMode("speaker")} data-testid="speaker-label">
            {seg.speaker || "+ pembicara"}
          </button>
        )}
        {seg.edited ? <span className="badge badge-info">diedit</span> : null}
        {seg.confidence != null && seg.confidence < 0.5 ? <span className="badge badge-busy">yakin rendah</span> : null}
      </div>
      {mode === "text" ? (
        <form onSubmit={(e) => { e.preventDefault(); save({ text }); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 100 }} aria-label="Teks segmen" />
          <div className="row">
            <button className="btn btn-small btn-primary">Simpan</button>
            <button type="button" className="btn btn-small" onClick={() => { setText(seg.text); setMode("view"); }}>Batal</button>
            {seg.original_text !== seg.text && <span className="muted small">Asli ASR: “{seg.original_text}”</span>}
          </div>
        </form>
      ) : (
        <p className="segment-text">
          {seg.text}{" "}
          <button className="linklike small" onClick={() => setMode("text")}>edit</button>
        </p>
      )}
      {err && <p className="error-text">{err}</p>}
    </div>
  );
}

function Speakers({ meeting, onChanged }: { meeting: MeetingDetail; onChanged: () => void }) {
  const [from, setFrom] = useState<string>(meeting.speakers[0]?.label ?? "");
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  if (!meeting.segments.length) return <Empty title="Belum ada transkrip" />;
  return (
    <>
      <p className="muted small">
        Diarisasi otomatis belum tersedia; beri nama pembicara pada tiap segmen di tab Transkrip, atau ganti nama sekaligus di sini.
      </p>
      <ul className="list" data-testid="speakers">
        {meeting.speakers.map((s) => (
          <li key={s.label ?? "_none"} className="row between">
            <span className="item-title">{s.label || "Tanpa label"}</span>
            <span className="muted small">{s.segments} segmen · {fmtTime(s.seconds)}</span>
          </li>
        ))}
      </ul>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await api<{ updated: number }>(`/api/meetings/${meeting.id}/speakers/rename`, {
            method: "POST", json: { old: from || null, new: to },
          });
          setMsg(`${r.updated} segmen diperbarui.`);
          setTo("");
          onChanged();
        }}
      >
        <h3 style={{ marginTop: 0 }}>Ganti / gabungkan label</h3>
        <label className="field">
          <span className="field-label">Dari</span>
          <select value={from} onChange={(e) => setFrom(e.target.value)}>
            {meeting.speakers.map((s) => (
              <option key={s.label ?? "_none"} value={s.label ?? ""}>{s.label || "Tanpa label"}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Menjadi</span>
          <input type="text" value={to} onChange={(e) => setTo(e.target.value)} maxLength={60} placeholder="Nama pembicara" />
        </label>
        <button className="btn btn-primary btn-small" disabled={!to.trim()}>Terapkan</button>
        {msg && <p className="muted small">{msg}</p>}
      </form>
    </>
  );
}
