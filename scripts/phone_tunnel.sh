#!/usr/bin/env bash
# Expose ONLY the phone page over a temporary HTTPS link (Cloudflare quick tunnel), so any phone on any network
# can send photos. The backend blocks every other path for tunnelled requests. Ctrl+C to stop.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/private/public_url.txt
LOG=data/private/tunnel.log
rm -f "$OUT"
trap 'rm -f "$OUT"; kill $PID 2>/dev/null || true' EXIT
cloudflared tunnel --no-autoupdate --url http://localhost:8000 >"$LOG" 2>&1 &
PID=$!
for _ in $(seq 1 60); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "${URL:-}" ] && { echo "Tunnel did not start; see $LOG"; exit 1; }
echo "$URL" > "$OUT"
echo "Phone link live: $URL/phone   (the Connect phone QR now points here)"
wait $PID
