# Evaluasi

Dijalankan 2026-10-04 dengan `cd backend && python scripts/evaluate.py` pada
container Linux x86_64, 4 vCPU, tanpa GPU, Python 3.11. Data uji sepenuhnya sintetis.
Hasil mentah: `eval-output/results.json` (tidak di-commit).

RSS = memori puncak proses benchmark Python; "subproses" = proses eksternal terbesar
(ffmpeg/espeak-ng/tesseract/worker) yang dijalankannya.

| Pengukuran | Status | Hasil |
|---|---|---|
| Kelengkapan ekstraksi PDF (buku 3 bab, header + nomor halaman berulang) | DIUKUR | recall token isi 1,00; urutan judul bab benar; 0 kebocoran header/footer; 3 header + 3 nomor halaman dihapus (tercatat) |
| OCR halaman pindaian (Tesseract `ind+eng`) | DIUKUR | CER 0,00 pada 2 kalimat bersih termasuk angka/tanggal/Rp; 0,65 dtk/halaman; RSS 103 MB |
| PDF besar 300 halaman | DIUKUR | 0,73 dtk (≈408 hlm/dtk); 30 bab terdeteksi; RSS 69 MB |
| TTS eSpeak NG (4 kalimat + 1 bab 6.850 karakter) | DIUKUR | bab → 576 dtk audio dalam 3,6 dtk (RTF 0,006); subproses ≤52 MB |
| Lafal / intelligibility / naturalness TTS | **TIDAK DIUKUR** | butuh uji dengar manusia (template di bawah) |
| WER, CER, akurasi nama/angka/akronim/istilah | **DILEWATI** | model Whisper tidak bisa diunduh (huggingface.co diblokir) |
| Diarization error rate | **DILEWATI** | tidak ada mesin diarisasi |
| Konkurensi: 6 job TTS, 1 worker | DIUKUR | 6/6 sukses, 1 percobaan masing-masing, 6,6 dtk |
| Konkurensi: 6 job TTS, 2 proses worker, 1 SQLite | DIUKUR | 6/6 sukses, tiap job tepat sekali (2 worker terpakai), 3,5 dtk |
| Memori server API + worker in-process | DIUKUR (manual) | puncak ~105 MB RSS setelah ekstraksi PDF + TTS 3 bab; container Docker ~60 MiB setelah alur yang sama |
| Batas hosting gratis nyata | **TIDAK DIUKUR** | belum ada deployment publik |

Catatan pada TTS: "kata per menit efektif" pada kalimat berangka rendah (77–121) karena angka
diucapkan sebagai banyak kata dan jeda kalimat; ini bukan kecepatan bicara sebenarnya.

## Tes otomatis

- `backend`: 86 tes lulus (`python -m pytest`) — ekstraksi & urutan bab, OCR fallback & deteksi
  pindaian, header/footer, PDF kosong/rusak/terenkripsi, validasi & konversi audio/video,
  timestamp antar-potongan, retry & pemulihan job, resume parsial, edit label pembicara,
  provenance item aksi, keluaran TTS & validitas MP3, kontrol akses, traversal path, retensi & hapus.
- `frontend`: 18 tes Playwright lulus — emulasi Pixel 7 (Chromium) + desktop: tanpa overflow
  horizontal, target sentuh ≥44 px, alur PDF→edit→audio→putar→kecepatan→unduh, posisi pemutar di
  atas navigasi, penyimpanan progres, edit transkrip/pembicara, seek dari timestamp, provenance di UI.
  Ini emulasi, **bukan** perangkat Android fisik.

## Cara mengukur WER setelah model tersedia

```bash
cd backend
python -m app.cli download-asr-model small
MI_WHISPER_MODEL=small python scripts/evaluate.py
```

Untuk hasil yang bermakna, ganti audio sintetis dengan rekaman uji **non-rahasia** dan transkrip
acuan yang dikoreksi manual, lalu gunakan `app.evaluation.wer`, `cer`, `term_accuracy`.

## Template uji dengar TTS (manusia)

Untuk tiap sampel di `scripts/evaluate.py:TTS_SAMPLES`, ≥3 pendengar penutur Indonesia memberi
skor 1–5: **Intelligibility** (dapat dipahami), **Pelafalan** (kata Indonesia, angka, akronim,
istilah Inggris), **Naturalness**. Laporkan rata-rata dan catatan kata yang salah ucap.
