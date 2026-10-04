"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, Capabilities, DocumentSummary, fmtBytes, fmtDate } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { Empty, ErrorBox, Loading, StatusBadge } from "@/components/ui";
import { UploadForm } from "@/components/UploadForm";

export default function AudiobooksPage() {
  const router = useRouter();
  const caps = useResource(() => api<Capabilities>("/api/capabilities"), []);
  const list = useResource(
    () => api<DocumentSummary[]>("/api/documents"),
    [],
    (d) => !!d?.some((x) => x.job && (x.job.status === "queued" || x.job.status === "running")),
    4000,
  );

  return (
    <>
      <h1>PDF Audiobook</h1>
      <UploadForm<DocumentSummary>
        endpoint="/api/documents"
        accept=".pdf,application/pdf"
        extensions={[".pdf"]}
        maxMb={caps.data?.limits.max_pdf_mb ?? 50}
        label="File PDF"
        hint={
          <>
            Maks {caps.data?.limits.max_pdf_mb ?? 50} MB / {caps.data?.limits.max_pdf_pages ?? 1500} halaman.{" "}
            {caps.data && (caps.data.ocr.available ? "PDF hasil pindaian akan di-OCR." : "OCR tidak tersedia: halaman pindaian akan ditandai untuk ditinjau.")}
          </>
        }
        onUploaded={(d) => router.push(`/audiobooks/view/?id=${d.id}`)}
        testId="pdf-upload"
      />

      <h2>Daftar dokumen</h2>
      <ErrorBox error={list.error} onRetry={list.refresh} />
      {list.loading && !list.data ? (
        <Loading />
      ) : !list.data?.length ? (
        <Empty title="Belum ada dokumen">Unggah PDF untuk membuat audiobook.</Empty>
      ) : (
        <ul className="list">
          {list.data.map((d) => (
            <li key={d.id}>
              <Link className="item-link" href={`/audiobooks/view/?id=${d.id}`}>
                <div className="row between">
                  <span className="item-title">{d.filename}</span>
                  <StatusBadge status={d.status} />
                </div>
                <span className="muted small">
                  {fmtDate(d.created_at)} · {fmtBytes(d.size_bytes)}
                  {d.page_count ? ` · ${d.page_count} hlm` : ""} · audio {d.with_audio}/{d.sections} bagian
                  {d.needs_review ? ` · ${d.needs_review} perlu ditinjau` : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
