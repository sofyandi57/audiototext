"""Aplikasi sederhana: upload rekaman suara/video -> langsung jadi teks transkrip
memakai OpenAI Whisper.

Jalankan dengan: streamlit run app.py
"""

import streamlit as st

from ffmpeg_utils import ensure_ffmpeg_on_path
from transcribe import transcribe_file

st.set_page_config(page_title="Audio ke Teks", page_icon="🎙️", layout="wide")
st.title("🎙️ Audio/Video → Teks (Whisper)")
st.caption(
    "Upload file rekaman suara (wav, mp3, m4a, ogg, dll) atau video (mp4, mov, dll), "
    "aplikasi ini otomatis mentranskripsinya jadi teks memakai OpenAI Whisper."
)

# --- Cek ffmpeg (wajib, dipakai Whisper untuk membaca semua format audio/video) ---
ffmpeg_dir = ensure_ffmpeg_on_path()
if ffmpeg_dir:
    st.success(f"ffmpeg terdeteksi: {ffmpeg_dir}", icon="✅")
else:
    st.error(
        "❌ ffmpeg tidak ditemukan di komputer ini. Whisper butuh ffmpeg untuk membaca "
        "file audio/video. Lihat README.md untuk cara instalasi ffmpeg.",
        icon="🚫",
    )

# --- Sidebar pengaturan ---
st.sidebar.header("Pengaturan")
model_size = st.sidebar.selectbox(
    "Ukuran model Whisper",
    options=["tiny", "base", "small", "medium", "large-v3"],
    index=2,
    help=(
        "Model lebih besar = lebih akurat tapi lebih lambat & butuh RAM lebih besar. "
        "Model diunduh otomatis saat pertama kali dipakai (butuh internet), lalu tersimpan "
        "di cache lokal untuk pemakaian berikutnya (tidak perlu unduh ulang)."
    ),
)
language_option = st.sidebar.selectbox(
    "Bahasa audio",
    options=["Deteksi otomatis", "Indonesia", "Inggris"],
    index=0,
)
language_map = {"Deteksi otomatis": None, "Indonesia": "id", "Inggris": "en"}
translate_to_en = st.sidebar.checkbox(
    "Terjemahkan ke Bahasa Inggris",
    value=False,
    help="Kalau dicentang, hasil transkrip langsung diterjemahkan ke Bahasa Inggris (fitur bawaan Whisper).",
)

st.divider()

uploaded_files = st.file_uploader(
    "Upload file audio/video (bisa pilih banyak sekaligus)",
    type=["wav", "mp3", "mp4", "m4a", "ogg", "flac", "aac", "wma", "avi", "mov", "mkv", "webm"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.write(f"**{len(uploaded_files)} file siap ditranskripsi.**")
    process_clicked = st.button("🚀 Transkripsi", type="primary", disabled=not ffmpeg_dir)
else:
    process_clicked = False

if process_clicked:
    results = []
    overall_progress = st.progress(0.0, text="Memulai...")
    for i, f in enumerate(uploaded_files):
        overall_progress.progress(
            i / len(uploaded_files),
            text=(
                f"Mentranskripsi ({i + 1}/{len(uploaded_files)}): {f.name} "
                "— mohon tunggu, bisa beberapa menit tergantung durasi & ukuran model..."
            ),
        )
        result = transcribe_file(
            f.read(),
            f.name,
            model_size=model_size,
            language=language_map[language_option],
            task="translate" if translate_to_en else "transcribe",
        )
        results.append({"name": f.name, **result})
    overall_progress.progress(1.0, text="Selesai.")
    st.session_state["hasil"] = results

if "hasil" in st.session_state:
    results = st.session_state["hasil"]
    st.subheader("Hasil")

    n_error = sum(1 for r in results if r["error"])
    if n_error:
        st.warning(f"{n_error} file gagal ditranskripsi — lihat detail di bawah.")

    for r in results:
        base_name = r["name"].rsplit(".", 1)[0]
        with st.expander(f"🎙️ {r['name']}", expanded=len(results) == 1):
            if r["error"]:
                st.error(f"Gagal diproses: {r['error']}")
                continue

            if r["language"]:
                st.caption(f"Bahasa terdeteksi: {r['language']}")

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "⬇️ Download Teks (.txt)",
                    r["text"].encode("utf-8"),
                    file_name=f"{base_name}.txt",
                    mime="text/plain",
                    key=f"dl_txt_{r['name']}",
                )
            with col2:
                st.download_button(
                    "⬇️ Download Subtitle (.srt)",
                    r["srt"].encode("utf-8"),
                    file_name=f"{base_name}.srt",
                    mime="text/plain",
                    key=f"dl_srt_{r['name']}",
                )

            tab_text, tab_srt = st.tabs(["Teks", "Subtitle (SRT)"])
            with tab_text:
                st.text_area("Transkrip", r["text"], height=250, key=f"txt_{r['name']}")
            with tab_srt:
                st.code(r["srt"], language="text")
