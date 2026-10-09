# Memakai di Android (Samsung S23 Ultra)

Aplikasi ini adalah **PWA** (web app yang bisa dipasang di layar utama). Tidak ada file APK, dan itu
disengaja: PWA berjalan di Chrome HP, tidak butuh Android SDK, dan ikut ter-update saat server di-update.

Status verifikasi: manifest, ikon, service worker, dan halaman offline **diuji otomatis** (Chromium
emulasi Pixel 7). Pemasangan di S23 Ultra fisik **belum diuji**; panduan di bawah mengikuti perilaku
Chrome Android yang umum.

## Cara kerja

Server (Python) jalan di Mac/laptop Anda. HP hanya menjadi layar dan pemutar audio.
Pemrosesan berat (OCR, TTS, transkripsi) terjadi di Mac, bukan di HP.

## Langkah 1 - jalankan server di Mac

```bash
git clone <url-repo> && cd audiototext
git checkout ccr-5c6ca82e-uh0c2z
brew install python@3.12 node ffmpeg espeak-ng tesseract tesseract-lang
./scripts/run-local.sh            # tambah --asr untuk transkripsi (unduh model dulu, butuh internet)
```

Skrip mencetak alamat untuk dibuka dari HP. Di Mac, `caffeinate` otomatis mencegah Mac tidur
saat server jalan (kalau Mac tidur, proses berhenti).

## Langkah 2 - buka dari S23 Ultra

Pilih salah satu. Penting: Chrome hanya menawarkan **"Install app"** pada alamat yang dianggap
aman (HTTPS, atau `localhost`). Alamat `http://192.168.x.x` biasa **tidak** dianggap aman.

| Cara | Hasil | Cocok untuk |
|---|---|---|
| **A. USB + `adb reverse`** | `http://localhost:8000` di HP, dianggap aman, bisa dipasang penuh | Uji coba paling mudah |
| **B. Wi-Fi + flag Chrome** | `http://IP-Mac:8000`, bisa dipasang setelah flag diaktifkan | HP percobaan tanpa kabel |
| **C. Wi-Fi saja** | Jalan di tab Chrome; "Tambahkan ke layar utama" hanya membuat pintasan | Cara tercepat, tanpa pemasangan penuh |

### Cara A: USB (disarankan untuk uji coba)

1. HP: Setelan -> Tentang ponsel -> Informasi perangkat lunak -> ketuk **Nomor versi** 7 kali ->
   kembali ke Setelan -> **Opsi pengembang** -> aktifkan **Debugging USB**.
2. Di Mac: `brew install android-platform-tools`, sambungkan kabel, izinkan debugging di HP.
3. `adb devices` (HP harus muncul sebagai `device`), lalu `adb reverse tcp:8000 tcp:8000`.
4. Chrome di HP: buka `http://localhost:8000`, menu titik tiga -> **Instal aplikasi** (atau tombol
   "Pasang" di banner aplikasi).

Kabel harus tetap terhubung selama dipakai.

### Cara B: Wi-Fi + flag Chrome (khusus HP percobaan)

1. HP dan Mac satu Wi-Fi. Alamat Mac: `ipconfig getifaddr en0`.
2. Chrome HP: buka `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, aktifkan,
   isi `http://IP-Mac:8000`, ketuk **Relaunch**.
3. Buka `http://IP-Mac:8000`, lalu **Instal aplikasi**.

Flag ini melemahkan keamanan untuk alamat tersebut; pakai hanya di HP percobaan dan jaringan rumah.
Kalau Mac menanyakan izin koneksi masuk untuk Python, pilih **Izinkan**.

### Jaringan umum

Kalau jaringan bukan milik Anda sendiri, set token di file `.env`:
`MI_ACCESS_TOKEN=<token-acak-panjang>`, lalu masuk lewat menu Settings di aplikasi.

## Langkah 3 - tes di HP (daftar periksa)

1. **PDF**: unggah PDF dari penyimpanan HP, tunggu "Siap ditinjau", periksa bab, buat audio, putar.
2. **Rekaman**: rekaman Samsung Voice Recorder berformat `.m4a` (folder Penyimpanan internal ->
   Recordings -> Voice Recorder) dan didukung. Unggah lewat pemilih file.
3. Pemutar audio: kecepatan putar, "lanjutkan mendengarkan", dan kunci layar saat audio berjalan.
4. Matikan Wi-Fi sebentar: aplikasi harus menampilkan halaman "Server tidak terjangkau", bukan blank.

## Masalah umum di Samsung

- **Audio berhenti saat layar mati / pindah aplikasi**: Setelan -> Aplikasi -> Chrome (atau aplikasi
  yang terpasang) -> Baterai -> pilih **Tidak dibatasi**. Matikan juga "Tidurkan aplikasi yang tidak dipakai".
- **Tidak ada opsi "Instal aplikasi"**: alamat belum dianggap aman (lihat tabel), atau Anda memakai
  Samsung Internet. Pakai Chrome untuk memasang.
- **Unggahan file besar gagal**: batas default 500 MB / 240 menit untuk rekaman, 50 MB untuk PDF
  (`MI_MAX_MEDIA_MB`, `MI_MAX_PDF_MB`).
- **Pembaruan tidak muncul**: tutup aplikasi dari daftar aplikasi terbaru lalu buka lagi (service worker
  memakai jaringan lebih dulu untuk halaman, jadi biasanya langsung terbarui).

## Privasi cache

Service worker hanya menyimpan file aplikasi (HTML/JS/CSS/ikon). Rute `/api/*` (unggahan,
transkrip, audio) **tidak pernah** disimpan di cache browser; ini diuji otomatis.

## Menjalankan server langsung di HP (Termux) - eksperimental

Belum diuji, dan keterbatasannya besar:

- Modul PDF -> audiobook kemungkinan bisa jalan (PyMuPDF, FFmpeg tersedia di Termux; `espeak` untuk TTS).
- **Transkripsi di HP kemungkinan tidak bisa**: `faster-whisper` bergantung pada `ctranslate2`, yang
  setahu saya tidak menyediakan paket siap pakai untuk Termux/Android (belum saya verifikasi). Jalur
  alternatifnya, whisper.cpp, belum diintegrasikan ke aplikasi ini.
- Aplikasi Termux dari Play Store sudah usang; pasang dari F-Droid.

Karena itu, untuk HP percobaan ini pendekatan yang realistis adalah Mac sebagai server dan HP sebagai klien.
