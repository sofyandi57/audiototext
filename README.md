# Meeting Intelligence Indonesia

Aplikasi web responsif (ramah Android) dengan dua modul, berjalan **di CPU tanpa GPU dan tanpa API berbayar**:

1. **Meeting Intelligence** — unggah rekaman rapat (audio/video) → transkrip bertimestamp
   Bahasa Indonesia → edit transkrip & label pembicara → ringkasan, keputusan, risiko,
   pertanyaan terbuka, dan tindak lanjut yang **masing-masing tertaut ke timestamp sumbernya**.
2. **PDF ke Audiobook** — unggah PDF → ekstraksi teks berurutan (bab, paragraf, OCR untuk
   halaman pindaian) → tinjau & koreksi teks → audio Bahasa Indonesia per bab (MP3) →
   putar, lanjutkan dari posisi terakhir, unduh per bab atau satu buku.

> Status jujur: lihat [docs/LIMITATIONS.md](docs/LIMITATIONS.md) dan
> [docs/EVALUATION.md](docs/EVALUATION.md). Ringkasnya: alur PDF→audiobook teruji end-to-end;
> pipeline transkripsi teruji dengan adapter ASR palsu, tetapi **transkripsi dengan model
> Whisper asli belum dapat diuji di lingkungan pengembangan** (unduhan model diblokir).
> Belum ada deployment publik yang terverifikasi.

## Struktur

```
backend/    FastAPI + worker + pipeline (Python)   → tests/ (pytest)
frontend/   Next.js (static export, TypeScript)   → e2e/ (Playwright, emulasi Android)
docs/       ARCHITECTURE.md, LIMITATIONS.md, EVALUATION.md
legacy/     aplikasi Streamlit lama (tidak dipakai lagi)
Dockerfile, docker-compose.yml, .env.example
```

## Menjalankan secara lokal (Linux/macOS/WSL)

Prasyarat: Python 3.11+, Node 20+, `ffmpeg`, `espeak-ng`; opsional `tesseract-ocr` +
`tesseract-ocr-ind` untuk OCR.

```bash
# Ubuntu/Debian
sudo apt install ffmpeg espeak-ng tesseract-ocr tesseract-ocr-ind

python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
pip install -r backend/requirements-asr.txt          # opsional: transkripsi

(cd frontend && npm ci && npm run build)             # menghasilkan frontend/out

cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
# buka http://localhost:8000   (dokumentasi API: /api/docs)
```

Model transkripsi **tidak** diunduh otomatis saat ada permintaan (agar request tidak macet).
Unduh sekali saat ada internet:

```bash
cd backend && python -m app.cli download-asr-model small   # tiny/base/small/medium
python -m app.cli capabilities                              # cek mesin yang tersedia
```

Mode pengembangan frontend (hot reload, `/api` diproksi ke backend :8000):
`cd frontend && npm run dev` → http://localhost:3000

## Menjalankan di Android

**Sebagai klien:** cukup buka URL server (mis. `http://IP-laptop:8000` di Wi-Fi yang sama)
di Chrome Android. UI dirancang mobile-first: navigasi bawah, target sentuh ≥44 px, pemutar
audio native dengan kontrol kecepatan, posisi dengar tersimpan.

**Sebagai server di HP (Termux, eksperimental, belum diuji di perangkat nyata):**

```bash
pkg install python nodejs ffmpeg espeak tesseract git
git clone <repo> && cd audiototext
pip install -r backend/requirements.txt     # PyMuPDF di Termux mungkin perlu dikompilasi
(cd frontend && npm ci && npm run build)
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Modul PDF→audiobook ringan (≈100 MB RAM). Transkripsi Whisper di HP akan lambat;
model `tiny`/`base` lebih realistis. `faster-whisper` mungkin tidak punya wheel untuk Termux.

## Docker

```bash
docker build -t meeting-intel .                         # tanpa ASR
docker build -t meeting-intel --build-arg WITH_ASR=1 .  # dengan faster-whisper
docker run -p 8000:8000 -v mi-data:/data meeting-intel

docker compose up --build        # API dan worker sebagai container terpisah
docker compose run --rm worker python -m app.cli download-asr-model small
```

Di balik proxy yang memeriksa TLS: tambahkan
`--secret id=ca_bundle,src=/path/ca.crt` saat `docker build`.

## Konfigurasi

Semua lewat variabel lingkungan `MI_*` — lihat [.env.example](.env.example). Penting untuk URL
publik: set **`MI_ACCESS_TOKEN`** (lalu masuk lewat halaman Settings). File unggahan tidak pernah
disajikan sebagai file statis; hanya lewat API, dan dihapus otomatis setelah
`MI_RETENTION_DAYS` (default 30) atau saat pengguna menghapusnya.

## Pengujian

```bash
cd backend && python -m pytest                       # 86 tes unit + integrasi
cd frontend && npx playwright test                    # 18 tes e2e (Pixel 7 + desktop)
cd backend && python scripts/evaluate.py              # metrik → eval-output/results.json
```

Korpus uji sepenuhnya sintetis (dibuat oleh `backend/tests/corpus.py`); jangan pernah
menggunakan rekaman rapat rahasia untuk pengujian di layanan publik.

## Lisensi komponen

FastAPI (MIT), PyMuPDF (AGPL-3.0 atau komersial — perhatikan bila mendistribusikan sebagai
layanan tertutup), faster-whisper & bobot Whisper (MIT), eSpeak NG (GPL-3.0, dipanggil sebagai
program terpisah), Tesseract (Apache-2.0), FFmpeg (LGPL/GPL tergantung build), Next.js (MIT).
