import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** Generate the synthetic corpus (no real documents/recordings are used). */
export default function globalSetup() {
  const root = path.resolve(__dirname, "..", "..");
  const out = path.join(root, "frontend", "test-results", "fixtures");
  fs.mkdirSync(out, { recursive: true });
  const python = process.env.PYTHON || path.join(root, ".venv", "bin", "python");
  execFileSync(python, ["-c", `
import sys; sys.path.insert(0, ".")
from pathlib import Path
from tests import corpus
o = Path(${JSON.stringify(out)})
corpus.make_book_pdf(o / "buku.pdf")
corpus.make_scanned_pdf(o / "pindaian.pdf")
corpus.make_tone(o / "rapat.wav", 6)
`], { cwd: path.join(root, "backend"), stdio: "inherit" });
}
