# Batasan yang diketahui

## Belum terverifikasi

| Fitur | Status | Kenapa / apa yang perlu dilakukan |
|---|---|---|
| Transkripsi dengan Whisper asli | **Belum diuji end-to-end** | Unduhan model dari huggingface.co diblokir di lingkungan pengembangan. Pipeline (konversi, chunking, offset timestamp, resume) diuji dengan adapter ASR palsu. Jalankan `python -m app.cli download-asr-model small` lalu `python scripts/evaluate.py` untuk mengukur WER. |
| WER, akurasi nama/angka/istilah | **Belum diukur** | Sama seperti di atas. Skrip pengukuran sudah ada. Catatan: audio uji di skrip memakai suara sintetis eSpeak — hasilnya bukan cerminan rapat nyata. Tetap butuh rekaman uji non-rahasia + transkrip acuan yang dikoreksi manual. |
| Diarisasi otomatis | **Tidak ada** | Model (pyannote dll.) butuh unduhan yang diblokir dan sering berlisensi terbatas. Label pembicara manual tersedia. |
| Piper TTS | Adapter saja | Belum ada suara Indonesia Piper yang terverifikasi (lisensi & kualitas). |
| Analisis via Ollama/LLM lokal | Adapter saja | Diuji hanya dengan respons tiruan. |
| Deployment publik | **Tidak ada** | Belum ada URL publik yang diverifikasi. |
| Termux / Android sebagai server | Belum diuji di perangkat | Instruksi bersifat best-effort. |

## Performa CPU

- PDF teks: ~400 halaman/dtk (PDF sintetis sederhana, 4 vCPU). PDF nyata dengan banyak gambar
  akan lebih lambat.
- OCR: ~0,65 dtk/halaman sederhana di 300 dpi; halaman padat bisa beberapa detik.
- eSpeak NG: sangat cepat (faktor real-time ≈0,006 untuk satu bab ~10 menit audio).
- Whisper di CPU (perkiraan umum, **belum diukur di sini**): `small` int8 kira-kira mendekati
  atau lebih lambat dari durasi audio pada CPU kecil; rapat 1 jam bisa memakan ≥1 jam di
  hosting gratis 1-2 vCPU. `tiny`/`base` jauh lebih cepat tetapi kurang akurat untuk Bahasa
  Indonesia campur istilah Inggris.
- Worker memproses satu job sekaligus per proses; job lain mengantre (terlihat di halaman Jobs).

## Kualitas TTS

- eSpeak NG terdengar robotik (sintesis formant). Lafal istilah Inggris (FastAPI, deployment)
  dibaca dengan aturan Indonesia. Angka dibaca oleh aturan eSpeak (mis. "2024" → kata);
  "Rp 1.500.000" dinormalisasi menjadi "rupiah 1.500.000" (urutan baca belum ideal).
- Naturalness/intelligibility **belum diukur** (butuh uji dengar manusia; template di EVALUATION.md).
- Suara browser (speechSynthesis) hanya pratinjau, tidak menghasilkan file, dan bergantung pada
  suara yang terpasang di perangkat (banyak HP tidak punya suara `id-ID` offline).

## Ekstraksi PDF

- Deteksi dua kolom sederhana (2 kolom saja); tabel, catatan kaki, dan teks melingkar belum
  ditangani khusus — tabel akan terbaca baris per baris.
- Heuristik judul bisa keliru pada PDF tanpa bookmark dengan tipografi tidak konsisten — judul
  dan teks dapat dikoreksi di editor.
- Header/footer yang hanya muncul di < 40% halaman tidak dihapus (sengaja konservatif).
- PDF terenkripsi berkata sandi ditolak dengan pesan jelas.

## Format yang didukung

- PDF saja untuk audiobook (bukan EPUB/DOCX).
- Rapat: wav, mp3, m4a, aac, ogg/oga/opus, flac, wma, amr, 3gp, mp4, mov, mkv, webm, avi —
  sejauh FFmpeg di server dapat mendekodenya. File tanpa trek audio ditolak.
- Batas default: PDF 50 MB / 1500 halaman; media 500 MB / 240 menit.

## Hosting gratis

- Layanan gratis umumnya: RAM 512 MB–1 GB, CPU dibagi, instance tidur saat idle, disk sementara.
  Konsekuensinya: (1) data hilang saat redeploy kecuali ada volume persisten; (2) job panjang
  terhenti saat instance tidur — job akan dilanjutkan setelah bangun (heartbeat recovery), tetapi
  tidak ada jaminan selesai; (3) model Whisper `small` (~500 MB disk, ~1 GB RAM saat jalan)
  kemungkinan tidak muat di tier terkecil.
- Tidak ada server inferensi always-on yang dijamin gratis. Rekomendasi: jalankan API+UI di
  hosting gratis untuk PDF→audiobook, dan worker transkripsi di laptop/PC lokal yang terhubung ke
  DB+storage yang sama — atau jalankan semuanya lokal.
- Image Docker ~1 GB (FFmpeg + Tesseract). Tanpa OCR bisa dikecilkan.
- SQLite cocok untuk satu host. Banyak host perlu storage bersama + DB server (belum dibuat).

## Lain-lain

- Belum ada akun multi-pengguna; satu token akses bersama.
- Ringkasan berbasis aturan bersifat ekstraktif (mengutip kalimat), recall terbatas: keputusan
  yang tidak memakai kata kunci ("sepakat", "diputuskan", dst.) tidak akan terdeteksi. Ini
  disengaja untuk menghindari keputusan yang dikarang.
- Tenggat disimpan sebagai frasa asli ("paling lambat hari Jumat"), tidak dikonversi ke tanggal.
