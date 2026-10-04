# Arsitektur

## Gambaran

```
Browser (Android/desktop)
   │  same-origin HTTP (cookie token opsional)
   ▼
FastAPI  ──────────────── serves frontend/out (Next.js static export)
   │  /api/*: upload, review/edit, status, unduh (Range)
   ▼
SQLite (WAL)  ◄──────────►  Worker (thread dalam API, atau `python -m app.worker` terpisah)
   │                           │
   ▼                           ▼
data/uploads, data/derived     Adapter: PDF/OCR · TTS · ASR · Diarisasi · Intelligence
(di luar direktori publik)     (FFmpeg, PyMuPDF, Tesseract, eSpeak NG, faster-whisper)
```

Tiga bagian dapat dipisah: frontend (file statis — bisa di CDN mana pun), API, dan worker
(beberapa proses/host berbagi DB+storage yang sama; diuji dengan 2 proses worker).

Mengapa static export disajikan oleh FastAPI: satu origin berarti cookie token juga berlaku
untuk `<audio src>` dan `<img src>`, tidak perlu CORS, dan cukup satu container/proses di
hosting gratis atau Termux. Mode `next dev` memproksi `/api` ke backend.

## Job queue (`backend/app/jobs.py`)

- Tabel `jobs` dengan status `queued → running → succeeded | failed | cancelled`, `stage`,
  `progress`, `attempts`, `heartbeat_at`.
- **Idempotensi**: kunci = `kind:target:hash(params)`; indeks unik parsial menjamin hanya satu
  job aktif per kunci (klik ganda/permintaan berulang mengembalikan job yang sama).
- **Klaim atomik** di `BEGIN IMMEDIATE` — aman untuk banyak worker.
- **Heartbeat** thread tiap 10 dtk; job `running` tanpa heartbeat > `MI_JOB_STALE_SECONDS`
  dikembalikan ke antrean (crash/restart container).
- **Retry**: error tak terduga di-retry otomatis s.d. `MI_JOB_MAX_ATTEMPTS`; `JobError`
  (mis. PDF rusak) langsung gagal dengan pesan yang bisa ditindaklanjuti. Retry manual
  memakai **ID job yang sama**. Pesan error internal tidak membocorkan path/stack trace.
- **Hasil parsial persisten**: TTS menyimpan audio per bab (dilewati bila hash teks + pengaturan
  sama); ASR menyimpan segmen per potongan audio (`meeting_chunks`). Retry melanjutkan, bukan
  mengulang dari nol (diuji).
- Satu job per worker sekaligus, karena ASR/TTS CPU-bound.

## Modul PDF → audiobook

1. `pdf/extract.py`: PyMuPDF `get_text("dict")` → baris + ukuran font + tebal. Urutan baca:
   deteksi tata letak dua kolom (kiri lalu kanan per pita vertikal). Halaman dengan < 25
   karakter: kosong → ditandai; ada gambar → OCR Tesseract (TSV, `ind+eng`, 300 dpi) bila
   tersedia, selain itu ditandai "perlu ditinjau". OCR berkeyakinan rendah juga ditandai.
2. `pdf/clean.py`: hanya baris pendek di pita margin atas/bawah 10% yang boleh dihapus —
   nomor halaman (regex) dan baris yang berulang di ≥40% halaman. **Setiap penghapusan dicatat**
   (halaman, teks, alasan) dan ditampilkan di UI. Penyambungan baris: perbaikan pemenggalan
   kata (`mengguna-` + `kan`) tanpa merusak reduplikasi (`anak-` + `anak` → `anak-anak`);
   paragraf yang terputus pergantian halaman disambung.
3. `pdf/chapters.py`: bookmark/outline PDF bila ada; jika tidak, heuristik judul (ukuran font
   ≥1,2× teks isi, pola `BAB/Chapter/Bagian`, baris tebal pendek). Bab dipecah menjadi bagian
   ≤ `MI_SECTION_MAX_CHARS` di batas paragraf/kalimat.
4. Review & edit: setiap bagian dapat diedit; audio yang dibuat dari teks lama ditandai
   "kedaluwarsa".
5. `tts/`: antarmuka `TTSEngine.synthesize(text, wav)`; `pipeline.py` menormalkan singkatan,
   memotong teks di batas kalimat, sintesis per potongan, gabung + encode MP3 (FFmpeg), lalu
   memvalidasi hasil dengan ffprobe. Mesin: eSpeak NG (terverifikasi), Piper (adapter, belum
   terverifikasi). Suara browser hanya pratinjau di frontend — **tidak** dianggap menghasilkan file.
6. Pratinjau PDF dirender server (PNG) — andal di semua browser Android, yang umumnya tidak
   menampilkan PDF inline. (PDF.js dipertimbangkan; ditolak karena beban JS di HP murah dan
   PNG dari PyMuPDF sudah cukup untuk pemeriksaan.)

## Modul rapat

1. Upload → validasi ekstensi, ukuran, `ffprobe` (harus ada trek audio, batas durasi), dedup SHA-256.
2. FFmpeg → WAV 16 kHz mono (format internal) + MP3 48 kbps untuk pemutar.
3. Potongan ~300 dtk; batas potongan digeser ke jeda hening terdekat (`silencedetect`) agar kata
   tidak terpotong. Timestamp segmen = awal potongan + timestamp lokal.
4. ASR adapter (`asr/faster_whisper.py`): CTranslate2 int8 CPU, VAD, `condition_on_previous_text=False`
   (mengurangi halusinasi berulang), glosarium sebagai `initial_prompt`.
5. Diarisasi: adapter terpisah; default "tidak tersedia" → label pembicara manual (per segmen
   atau ganti nama massal).
6. Intelligence: `intelligence/rules.py` (pola Bahasa Indonesia, ringkasan ekstraktif) atau
   Ollama lokal opsional. Keduanya melewati `provenance.validate`: item tanpa rujukan segmen
   valid ditolak; timestamp diambil dari segmen; PIC/tenggat hanya disimpan bila tertulis di
   segmen yang dikutip, selain itu "belum dikonfirmasi".

## Keamanan & privasi

- Data di `MI_DATA_DIR`, tidak pernah di-mount statis; ID divalidasi regex + pemeriksaan path
  (anti traversal) di `storage.py`.
- Token akses opsional (header Bearer atau cookie HttpOnly), `/api/health` tetap publik.
- Body > batas ditolak sebelum parsing multipart; respons `/api` `Cache-Control: no-store`.
- Retensi otomatis + hapus manual (file asli, turunan, baris DB).
