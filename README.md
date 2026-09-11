# Audio/Video → Teks (Whisper)

Aplikasi Streamlit sederhana untuk transkripsi rekaman suara atau video menjadi
teks, memakai [OpenAI Whisper](https://github.com/openai/whisper).

Mendukung upload file: `wav`, `mp3`, `mp4`, `m4a`, `ogg`, `flac`, `aac`, `wma`,
`avi`, `mov`, `mkv`, `webm`. Whisper mendekode semua format ini lewat ffmpeg,
jadi format video juga otomatis diambil audionya lalu ditranskrip.

## Cara menjalankan

1. Pastikan Python 3.12 sudah terpasang.
2. Pastikan **ffmpeg** sudah terpasang (lihat bagian di bawah).
3. Double-click `jalankan.bat`.
   - Pertama kali dijalankan, langkah install library (termasuk `torch`) bisa
     memakan waktu beberapa menit karena ukurannya besar (~2 GB).
   - Browser akan otomatis terbuka ke aplikasi Streamlit.
4. Upload file audio/video, atur model & bahasa di sidebar, lalu klik
   **Transkripsi**.
5. Hasil bisa didownload sebagai `.txt` (teks polos) atau `.srt` (subtitle
   dengan timestamp).

## Instalasi ffmpeg (wajib)

Whisper memanggil `ffmpeg` sebagai program terpisah untuk membaca file
audio/video, jadi ffmpeg harus tersedia di komputer. Ada dua cara:

**Cara 1 — pakai winget (paling gampang):**

```bash
winget install ffmpeg
```

Lalu restart terminal/`jalankan.bat` supaya PATH ter-refresh.

**Cara 2 — portable, tanpa install:**

1. Download build ffmpeg untuk Windows dari
   [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (pilih
   "essentials build", format zip).
2. Extract, lalu salin folder `bin` (isinya `ffmpeg.exe`, dll) ke dalam folder
   aplikasi ini dengan nama `ffmpeg-portable`, sehingga strukturnya:
   `audio-to-text-app/ffmpeg-portable/ffmpeg.exe`.
3. Aplikasi otomatis mendeteksi folder ini tanpa perlu setting PATH manual.

Kalau ffmpeg belum ditemukan, aplikasi akan menampilkan pesan error di bagian
atas halaman dan tombol Transkripsi akan dinonaktifkan.

## Tentang model Whisper

- Model dipilih di sidebar: `tiny`, `base`, `small`, `medium`, `large-v3`.
  Makin besar makin akurat tapi makin lambat & makin besar pemakaian RAM.
  Untuk PC tanpa GPU, `base` atau `small` biasanya sudah cukup baik dan masih
  cepat.
- Model diunduh otomatis dari server OpenAI saat pertama kali dipakai (butuh
  internet), lalu disimpan di cache lokal (`~/.cache/whisper`) sehingga
  pemakaian berikutnya tidak perlu unduh ulang meskipun sedang offline.
- Ada opsi "Terjemahkan ke Bahasa Inggris" di sidebar — kalau dicentang, hasil
  transkrip langsung diterjemahkan ke Inggris (fitur bawaan Whisper), bukan
  hanya ditranskrip di bahasa aslinya.

## Catatan

- Aplikasi ini belum dibundel jadi `.exe` portable (seperti
  `pdf-to-markdown-app`) karena `torch` + model Whisper ukurannya besar,
  sehingga hasil bundling akan sangat besar. Cara menjalankan yang
  direkomendasikan adalah lewat `jalankan.bat` dengan Python terpasang.
- Proses transkripsi berjalan di CPU secara default. Untuk mempercepat di PC
  dengan GPU NVIDIA, install `torch` versi CUDA sesuai
  [panduan resmi PyTorch](https://pytorch.org/get-started/locally/) sebelum
  menjalankan `jalankan.bat` (atau jalankan `pip install` manual dengan index
  URL CUDA-nya).
