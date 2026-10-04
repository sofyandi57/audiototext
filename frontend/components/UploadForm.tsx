"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, fmtBytes, upload } from "@/lib/api";
import { Progress } from "./ui";

export function UploadForm<T>({
  endpoint,
  accept,
  extensions,
  maxMb,
  label,
  hint,
  children,
  onUploaded,
  testId,
}: {
  endpoint: string;
  accept: string;
  extensions: string[];
  maxMb: number;
  label: string;
  hint?: ReactNode;
  children?: ReactNode; // extra form fields
  onUploaded: (result: T) => void;
  testId?: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const validate = (f: File): string | null => {
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (!extensions.includes(ext)) return `Format ${ext} tidak didukung. Gunakan: ${extensions.join(", ")}.`;
    if (f.size > maxMb * 1024 * 1024) return `File ${fmtBytes(f.size)} melebihi batas ${maxMb} MB.`;
    if (f.size === 0) return "File kosong.";
    return null;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return setError("Pilih file terlebih dahulu.");
    const problem = validate(file);
    if (problem) return setError(problem);
    setError(null);
    setNotice(null);
    setProgress(0);
    const data = new FormData(formRef.current!);
    data.set("file", file, file.name);
    try {
      const res = await upload<T & { duplicate?: boolean }>(endpoint, data, setProgress);
      if (res.duplicate) setNotice("File yang sama sudah pernah diunggah — membuka hasil yang ada.");
      setFile(null);
      formRef.current?.reset();
      onUploaded(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setProgress(null);
    }
  };

  return (
    <form ref={formRef} className="card upload" onSubmit={submit} data-testid={testId}>
      <label className="field">
        <span className="field-label">{label}</span>
        <input
          type="file"
          name="file"
          accept={accept}
          onChange={(e) => {
            const f = e.target.files?.[0] || null;
            setFile(f);
            setError(f ? validate(f) : null);
          }}
        />
      </label>
      {file && (
        <p className="muted small">
          {file.name} · {fmtBytes(file.size)}
        </p>
      )}
      {hint && <p className="muted small">{hint}</p>}
      {children}
      {progress !== null && (
        <div>
          <Progress value={progress} label="Unggahan" />
          <p className="muted small">Mengunggah… {Math.round(progress * 100)}%</p>
        </div>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="muted small">{notice}</p>}
      <button className="btn btn-primary" type="submit" disabled={progress !== null}>
        {progress !== null ? "Mengunggah…" : "Unggah & proses"}
      </button>
      <p className="muted small">Unggahan berhasil belum berarti pemrosesan berhasil — pantau statusnya di halaman hasil.</p>
    </form>
  );
}
