"""Test helper: give an uploaded meeting a transcript so the UI can be tested
without an ASR model (model downloads are unavailable in CI)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.config import Settings  # noqa: E402
from app.db import Database, new_id  # noqa: E402

data_dir, meeting_id = sys.argv[1], sys.argv[2]
db = Database(Settings(data_dir=Path(data_dir), _env_file=None).db_path)
lines = [
    ("Rina", 0.0, 1.5, "Selamat pagi, kita mulai rapat evaluasi aplikasi transkripsi."),
    (None, 1.5, 3.0, "Setelah diskusi kita sepakat memakai FastAPI untuk backend."),
    ("Rina", 3.0, 4.5, "Tolong Budi siapkan dokumentasi API paling lambat hari Jumat."),
    (None, 4.5, 6.0, "Risikonya server gratis terlambat memproses audio panjang."),
]
db.execute("DELETE FROM segments WHERE meeting_id=?", (meeting_id,))
for i, (spk, a, b, t) in enumerate(lines):
    db.execute(
        "INSERT INTO segments (id, meeting_id, chunk_idx, idx, start, end, text, original_text, speaker)"
        " VALUES (?,?,?,?,?,?,?,?,?)", (new_id("seg"), meeting_id, 0, i, a, b, t, t, spk))
db.execute("UPDATE meetings SET status='ready', error=NULL WHERE id=?", (meeting_id,))
print("seeded")
