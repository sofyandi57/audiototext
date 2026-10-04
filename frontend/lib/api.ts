// Same-origin API client. Cookies carry the optional access token so that
// <audio src> and <img src> requests are authorised too.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let msg = `Permintaan gagal (${res.status}).`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") msg = body.detail;
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 401) msg = msg || "Butuh token akses.";
  return new ApiError(res.status, msg);
}

export async function api<T = unknown>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init || {};
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      ...rest,
      headers: json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "Tidak dapat terhubung ke server. Periksa koneksi internet.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

/** Upload with progress (fetch has no upload progress events). */
export function upload<T>(path: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(0, "Unggahan terputus. Periksa koneksi lalu coba lagi."));
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, body?.detail || `Unggahan gagal (${xhr.status}).`));
    };
    xhr.send(form);
  });
}

// ---- types ---------------------------------------------------------------

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  kind: string;
  target_id: string;
  status: JobStatus;
  stage: string | null;
  progress: number;
  error: string | null;
  attempts: number;
  max_attempts: number;
  created_at: number;
  updated_at: number;
  target_name?: string | null;
  target_type?: "document" | "meeting";
}

export interface Section {
  id: string;
  idx: number;
  title: string;
  level: number;
  text: string;
  start_page: number | null;
  end_page: number | null;
  edited: number;
  needs_review: number;
  audio_status: "none" | "done" | "failed" | "skipped";
  audio_duration: number | null;
  audio_engine: string | null;
  audio_error: string | null;
  audio_stale: boolean;
  char_count: number;
}

export interface DocPage {
  page_no: number;
  char_count: number;
  text_source: "text" | "ocr" | "none";
  needs_review: number;
  review_reason: string | null;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number | null;
  status: string;
  error: string | null;
  created_at: number;
  sections: number;
  with_audio: number;
  needs_review: number;
  job: Job | null;
  duplicate?: boolean;
}

export interface CleaningReport {
  removed: { page: number; text: string; reason: string }[];
  summary: Record<string, number>;
  dehyphenated: number;
  merged_across_pages: number;
  used_outline: boolean;
  ocr_pages: number[];
  review_pages: { page: number; reason: string }[];
  warning?: string;
}

export interface DocumentDetail extends Omit<DocumentSummary, "sections"> {
  sections: Section[];
  pages: DocPage[];
  cleaning_report: CleaningReport | null;
  jobs: Job[];
}

export interface Segment {
  id: string;
  idx: number;
  start: number;
  end: number;
  text: string;
  original_text: string;
  speaker: string | null;
  confidence: number | null;
  edited: number;
}

export interface Insight {
  id: string;
  kind: "summary" | "decision" | "risk" | "question" | "action";
  text: string;
  owner: string | null;
  owner_confirmed: boolean;
  deadline: string | null;
  deadline_confirmed: boolean;
  segment_ids: string[];
  start: number;
  end: number;
  engine: string;
}

export interface MeetingSummary {
  id: string;
  filename: string;
  title: string | null;
  duration: number | null;
  status: string;
  error: string | null;
  created_at: number;
  segment_count: number;
  job: Job | null;
  duplicate?: boolean;
}

export interface MeetingDetail extends MeetingSummary {
  segments: Segment[];
  speakers: { label: string | null; segments: number; seconds: number }[];
  insights: Insight[];
  jobs: { meeting_transcribe: Job | null; meeting_analyze: Job | null };
  has_audio: boolean;
  asr_model: string | null;
  language: string | null;
}

export interface EngineInfo {
  name: string;
  available: boolean;
  reason: string | null;
  license?: string;
  file_output?: boolean;
  voices?: { id: string; label: string }[];
  notes?: string;
  model?: string;
}

export interface Capabilities {
  ffmpeg: boolean;
  ocr: { available: boolean; languages?: string | null; reason?: string };
  tts: EngineInfo[];
  tts_default: string;
  asr: EngineInfo;
  diarization: EngineInfo;
  intelligence: EngineInfo;
  limits: { max_pdf_mb: number; max_media_mb: number; max_pdf_pages: number; max_media_minutes: number };
  retention_days: number;
}

// ---- formatting ----------------------------------------------------------

export function fmtTime(sec: number | null | undefined): string {
  if (sec == null || !isFinite(sec)) return "--:--";
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(r).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "Antre",
  running: "Diproses",
  succeeded: "Selesai",
  failed: "Gagal",
  cancelled: "Dibatalkan",
  uploaded: "Terunggah",
  extracting: "Mengekstrak",
  review: "Siap ditinjau",
  generating: "Membuat audio",
  ready: "Siap",
  converting: "Mengonversi",
  transcribing: "Mentranskripsi",
  analyzing: "Menganalisis",
};

export const JOB_LABEL: Record<string, string> = {
  pdf_extract: "Ekstraksi PDF",
  tts_generate: "Pembuatan audio",
  meeting_transcribe: "Transkripsi rapat",
  meeting_analyze: "Analisis rapat",
};
