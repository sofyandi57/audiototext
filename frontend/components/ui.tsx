"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { api, ApiError, Job, JOB_LABEL, STATUS_LABEL } from "@/lib/api";

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "failed"
      ? "bad"
      : status === "ready" || status === "succeeded"
        ? "good"
        : status === "review"
          ? "info"
          : status === "cancelled"
            ? "muted"
            : "busy";
  return <span className={`badge badge-${tone}`}>{STATUS_LABEL[status] || status}</span>;
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError | string | null; onRetry?: () => void }) {
  if (!error) return null;
  const msg = typeof error === "string" ? error : error.message;
  const needsAuth = typeof error !== "string" && error.status === 401;
  return (
    <div className="alert alert-error" role="alert">
      <p>{msg}</p>
      <div className="row">
        {needsAuth && (
          <Link className="btn btn-small" href="/settings/">
            Masukkan token
          </Link>
        )}
        {onRetry && (
          <button className="btn btn-small" onClick={onRetry}>
            Coba lagi
          </button>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children}
    </div>
  );
}

export function Loading({ label = "Memuat…" }: { label?: string }) {
  return (
    <div className="loading" aria-live="polite">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

/** Shows a job's state, stage, progress, error and retry/cancel actions. */
export function JobPanel({ job, onChange, compact }: { job: Job | null; onChange?: () => void; compact?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!job) return null;
  const act = async (action: "retry" | "cancel") => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/jobs/${job.id}/${action}`, { method: "POST" });
      onChange?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const active = job.status === "queued" || job.status === "running";
  return (
    <div className={`job ${compact ? "job-compact" : ""}`} data-testid="job-panel" data-status={job.status}>
      <div className="row between">
        <strong>{JOB_LABEL[job.kind] || job.kind}</strong>
        <StatusBadge status={job.status} />
      </div>
      {active && (
        <>
          <Progress value={job.progress} label={job.stage || ""} />
          <p className="muted small">
            Tahap: {job.stage || "menunggu"}
            {job.attempts > 1 ? ` · percobaan ${job.attempts}/${job.max_attempts}` : ""}
          </p>
        </>
      )}
      {job.error && (job.status === "failed" || job.status === "queued") && (
        <p className={job.status === "failed" ? "error-text" : "muted small"}>
          {job.status === "queued" ? "Percobaan sebelumnya gagal: " : ""}
          {job.error}
        </p>
      )}
      {err && <p className="error-text">{err}</p>}
      <div className="row">
        {(job.status === "failed" || job.status === "cancelled") && (
          <button className="btn btn-small" disabled={busy} onClick={() => act("retry")}>
            Ulangi
          </button>
        )}
        {active && (
          <button className="btn btn-small btn-ghost" disabled={busy} onClick={() => act("cancel")}>
            Batalkan
          </button>
        )}
      </div>
    </div>
  );
}

export function ConfirmButton({
  children,
  confirmText,
  onConfirm,
  className = "btn btn-danger btn-small",
}: {
  children: ReactNode;
  confirmText: string;
  onConfirm: () => void | Promise<void>;
  className?: string;
}) {
  return (
    <button
      className={className}
      onClick={async () => {
        if (window.confirm(confirmText)) await onConfirm();
      }}
    >
      {children}
    </button>
  );
}
