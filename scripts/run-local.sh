#!/usr/bin/env bash
# One-command local run (macOS / Linux). Creates .venv, installs, builds the UI, starts the server
# and prints the addresses to open from your phone.
#
#   ./scripts/run-local.sh                 # PDF -> audiobook + upload/edit (no speech recognition)
#   ./scripts/run-local.sh --asr           # also install faster-whisper
#   ./scripts/run-local.sh --asr --model medium
#   ./scripts/run-local.sh --check         # only check prerequisites
#   PORT=9000 ./scripts/run-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
WITH_ASR=0; MODEL=""; CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --asr) WITH_ASR=1 ;;
    --model) MODEL="${2:-}"; shift ;;
    --check) CHECK_ONLY=1 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

OS="$(uname -s)"
missing=()
need() { command -v "$1" >/dev/null 2>&1 || missing+=("$1"); }
need python3; need node; need npm; need ffmpeg; need ffprobe; need espeak-ng
HAVE_OCR=1; command -v tesseract >/dev/null 2>&1 || HAVE_OCR=0

if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required tools: ${missing[*]}" >&2
  if [ "$OS" = "Darwin" ]; then
    echo "Install with:  brew install python@3.12 node ffmpeg espeak-ng tesseract tesseract-lang" >&2
  else
    echo "Install with:  sudo apt install python3-venv nodejs npm ffmpeg espeak-ng tesseract-ocr tesseract-ocr-ind" >&2
  fi
  exit 1
fi
if [ "$HAVE_OCR" = 0 ]; then
  echo "Note: tesseract not found. Scanned PDF pages will be flagged for review instead of OCR'd."
fi
if ! espeak-ng --voices=id 2>/dev/null | grep -q " id "; then
  echo "Warning: espeak-ng has no Indonesian voice ('id'); server-side audio will be unavailable." >&2
fi
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' || { echo "Python >= 3.10 required (found $PYV)" >&2; exit 1; }
echo "Prerequisites OK (python $PYV, node $(node -v))."
[ "$CHECK_ONLY" = 1 ] && exit 0

cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt
if [ "$WITH_ASR" = 1 ]; then
  pip install --quiet -r backend/requirements-asr.txt
  (cd backend && python -m app.cli download-asr-model "${MODEL:-small}")
fi
if [ ! -f frontend/out/index.html ]; then
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi

lan_ip() {
  if [ "$OS" = "Darwin" ]; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
  else
    hostname -I 2>/dev/null | awk '{print $1}' || true
  fi
}
IP="$(lan_ip)"
cat <<MSG

  Server:            http://localhost:$PORT
  From phone (Wi-Fi): http://${IP:-<IP-komputer>}:$PORT
  From phone (USB):   adb reverse tcp:$PORT tcp:$PORT   then open http://localhost:$PORT on the phone
  Stop with Ctrl+C. Data is stored in ./data (not committed).

MSG

export MI_DATA_DIR="${MI_DATA_DIR:-$ROOT/data}"
export MI_FRONTEND_DIR="${MI_FRONTEND_DIR:-$ROOT/frontend/out}"
[ -n "$MODEL" ] && export MI_WHISPER_MODEL="$MODEL"
cd backend
RUN=(uvicorn app.main:app --host 0.0.0.0 --port "$PORT")
# keep a Mac awake while the server runs (sleep would stop jobs)
if [ "$OS" = "Darwin" ] && command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i "${RUN[@]}"
fi
exec "${RUN[@]}"
