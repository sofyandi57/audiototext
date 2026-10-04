"use client";

import Link from "next/link";
import { api, Capabilities, DocumentSummary, fmtDate, MeetingSummary } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { ErrorBox, Loading, StatusBadge } from "@/components/ui";

export default function Dashboard() {
  const caps = useResource(() => api<Capabilities>("/api/capabilities"), []);
  const meetings = useResource(() => api<MeetingSummary[]>("/api/meetings"), []);
  const docs = useResource(() => api<DocumentSummary[]>("/api/documents"), []);
  const c = caps.data;

  return (
    <>
      <h1>Dashboard</h1>
      <ErrorBox error={caps.error} />
      <div className="grid grid-2">
        <section className="card" aria-labelledby="mod-meeting">
          <h2 id="mod-meeting">Meeting Intelligence</h2>
          <p className="muted small">Unggah rekaman rapat (audio/video) untuk transkrip bertimestamp, ringkasan, keputusan, dan tindak lanjut.</p>
          {c && (
            <p className="small">
              Transkripsi:{" "}
              {c.asr.available ? (
                <span className="badge badge-good">tersedia ({c.asr.model})</span>
              ) : (
                <span className="badge badge-bad">belum tersedia</span>
              )}
            </p>
          )}
          {c && !c.asr.available && <p className="muted small">{c.asr.reason}</p>}
          <Link className="btn btn-primary" href="/meetings/">
            Buka Rapat
          </Link>
          <Recent loading={meetings.loading} items={(meetings.data || []).slice(0, 3).map((m) => ({
            href: `/meetings/view/?id=${m.id}`, title: m.title || m.filename, status: m.status, ts: m.created_at }))} />
        </section>
        <section className="card" aria-labelledby="mod-book">
          <h2 id="mod-book">PDF ke Audiobook</h2>
          <p className="muted small">Unggah PDF, periksa & koreksi teks hasil ekstraksi, lalu buat audio per bab.</p>
          {c && (
            <p className="small">
              Suara:{" "}
              {c.tts.some((t) => t.available) ? (
                <span className="badge badge-good">{c.tts.filter((t) => t.available).map((t) => t.name).join(", ")}</span>
              ) : (
                <span className="badge badge-bad">tidak ada mesin TTS</span>
              )}{" "}
              · OCR:{" "}
              <span className={`badge ${c.ocr.available ? "badge-good" : "badge-muted"}`}>
                {c.ocr.available ? "tersedia" : "tidak tersedia"}
              </span>
            </p>
          )}
          <Link className="btn btn-primary" href="/audiobooks/">
            Buka Audiobook
          </Link>
          <Recent loading={docs.loading} items={(docs.data || []).slice(0, 3).map((d) => ({
            href: `/audiobooks/view/?id=${d.id}`, title: d.filename, status: d.status, ts: d.created_at }))} />
        </section>
      </div>
    </>
  );
}

function Recent({ items, loading }: { loading: boolean; items: { href: string; title: string; status: string; ts: number }[] }) {
  if (loading) return <Loading />;
  if (!items.length) return <p className="muted small">Belum ada file.</p>;
  return (
    <ul className="list" style={{ marginTop: 10 }}>
      {items.map((it) => (
        <li key={it.href}>
          <Link className="item-link" href={it.href}>
            <div className="row between">
              <span className="item-title">{it.title}</span>
              <StatusBadge status={it.status} />
            </div>
            <span className="muted small">{fmtDate(it.ts)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
