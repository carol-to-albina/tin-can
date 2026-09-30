#!/usr/bin/env bash
# Start the public TinCan demo and put it on the internet through Cloudflare.
#
#   web/present.sh                     quick tunnel, random https://*.trycloudflare.com address
#   TINCAN_TUNNEL=tincan TINCAN_PUBLIC_URL=https://tincan.example.com web/present.sh
#                                      a named tunnel you set up with `cloudflared tunnel create`
#
# Extra flags go to serve.py, e.g. --credit 0.40 --budget 4
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8790}"
LOG="$(mktemp -t tincan-tunnel.XXXXXX)"
command -v cloudflared >/dev/null || { echo "cloudflared is not installed" >&2; exit 1; }

cleanup() { kill "${SERVER:-}" "${TUNNEL:-}" 2>/dev/null || true; rm -f "$LOG"; }
trap cleanup EXIT INT TERM

if [ -n "${TINCAN_TUNNEL:-}" ]; then
  cloudflared tunnel --no-autoupdate run --url "http://127.0.0.1:$PORT" "$TINCAN_TUNNEL" >"$LOG" 2>&1 &
  TUNNEL=$!
  URL="${TINCAN_PUBLIC_URL:?set TINCAN_PUBLIC_URL to the tunnel hostname}"
else
  cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
  TUNNEL=$!
  for _ in $(seq 1 60); do
    URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)"
    [ -n "$URL" ] && break
    sleep 0.5
  done
  [ -n "${URL:-}" ] || { echo "the tunnel did not come up:" >&2; cat "$LOG" >&2; exit 1; }
fi

TINCAN_PUBLIC_URL="$URL" python3 -u web/serve.py --demo --port "$PORT" "$@" &
SERVER=$!
for _ in $(seq 1 20); do [ -s "$HOME/.config/tincan/host-token" ] && curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.3; done

echo
echo "  Guests:     $URL/"
echo "  Your seat:  $URL/host#$(cat "$HOME/.config/tincan/host-token")"
echo "  Scripted:   $URL/duet"
echo
echo "  Keep this window open. Ctrl+C stops the demo and the tunnel."
wait "$SERVER"
