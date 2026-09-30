#!/usr/bin/env bash
# Deploy the demo to Cloudflare. The landing page plays the v2 film and nothing else,
# so this refuses to deploy if web/media/tincan-film.mp4 is any other file.
set -euo pipefail
cd "$(dirname "$0")"

V2_SHA256="ed23b7d7fca4e9bea71decfe489c55a577bf17632dc20561aeb8ca310c94d8c7"  # demo-video/tincan-demo-v2.mp4
got="$(sha256sum ../web/media/tincan-film.mp4 | cut -d' ' -f1)"
if [ "$got" != "$V2_SHA256" ]; then
  echo "web/media/tincan-film.mp4 is not the v2 film (sha256 $got). The landing page shows v2 only." >&2
  exit 1
fi
npx wrangler@4 deploy "$@"
