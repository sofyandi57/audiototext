"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, Capabilities, fmtDate, fmtTime, MeetingSummary } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { Empty, ErrorBox, Loading, StatusBadge } from "@/components/ui";
import { UploadForm } from "@/components/UploadForm";

const EXT = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".amr", ".3gp",
  ".mp4", ".mov", ".mkv", ".webm", ".avi"];

export default function MeetingsPage() {
  const router = useRouter();
  const caps = useResource(() => api<Capabilities>("/api/capabilities"), []);
  const list = useResource(
    () => api<MeetingSummary[]>("/api/meetings"),
    [],
    (d) => !!d?.some((m) => m.job && (m.job.status === "queued" || m.job.status === "running")),
    4000,
  );

  return (
    <>
      <h1>Rapat</h1>
      {caps.data && !caps.data.asr.available && (
        <div className="alert alert-warn" data-testid="asr-unavailable">
          <p><strong>Transkripsi belum tersedia di server ini.</strong></p>
          <p className="small">{caps.data.asr.reason}</p>
          <p className="small">Anda tetap bisa mengunggah; file disimpan dan dapat diproses ulang setelah model dipasang.</p>
        </div>
      )}
      <UploadForm<MeetingSummary>
        endpoint="/api/meetings"
        accept={EXT.join(",") + ",audio/*,video/*"}
        extensions={EXT}
        maxMb={caps.data?.limits.max_media_mb ?? 500}
        label="Rekaman rapat (audio atau video)"
        hint={`Maks ${caps.data?.limits.max_media_mb ?? 500} MB / ${caps.data?.limits.max_media_minutes ?? 240} menit.`}
        onUploaded={(m) => router.push(`/meetings/view/?id=${m.id}`)}
        testId="meeting-upload"
      >
        <label className="field">
          <span className="field-label">Judul (opsional)</span>
          <input type="text" name="title" maxLength={200} placeholder="Rapat mingguan tim" />
        </label>
        <label className="field">
          <span className="field-label">Bahasa</span>
          <select name="language" defaultValue="id">
            <option value="id">Bahasa Indonesia</option>
            <option value="en">English</option>
            <option value="auto">Deteksi otomatis</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">Glosarium istilah/nama (opsional)</span>
          <input type="text" name="glossary" maxLength={1000} placeholder="Contoh: FastAPI, deployment, Bu Rina, OKR" />
        </label>
      </UploadForm>

      <h2>Daftar rapat</h2>
      <ErrorBox error={list.error} onRetry={list.refresh} />
      {list.loading && !list.data ? (
        <Loading />
      ) : !list.data?.length ? (
        <Empty title="Belum ada rapat">Unggah rekaman untuk memulai.</Empty>
      ) : (
        <ul className="list">
          {list.data.map((m) => (
            <li key={m.id}>
              <Link className="item-link" href={`/meetings/view/?id=${m.id}`}>
                <div className="row between">
                  <span className="item-title">{m.title || m.filename}</span>
                  <StatusBadge status={m.status} />
                </div>
                <span className="muted small">
                  {fmtDate(m.created_at)} · {fmtTime(m.duration)} · {m.segment_count} segmen
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
