#!/usr/bin/env bash
# Checks the running stack from the host: health, local sign-in, an authorized read.
# Free: no model or speech provider is called.
#
# --paid also streams fixtures/sample.wav into /v4/listen and waits for the
# finished conversation. That spends Deepgram and OpenAI credit.
set -euo pipefail
cd "$(dirname "$0")"

paid=0
if [ "${1:-}" = --paid ]; then paid=1; fi

BACKEND=${BACKEND:-http://127.0.0.1:8000}
DESKTOP_BACKEND=${DESKTOP_BACKEND:-http://127.0.0.1:10201}
AUTH_EMULATOR=${AUTH_EMULATOR:-http://127.0.0.1:9099}
# The Auth emulator accepts any API key.
FIREBASE_API_KEY=local-firebase-auth-emulator-api-key
UID_LOCAL=${UID_LOCAL:-local-dev-user}

failed=0
pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failed=1; }

check_url() {
  if curl -fsS -o /dev/null --max-time 10 "$2"; then pass "$1"; else fail "$1 ($2)"; fi
}

json_field() { python3 -c 'import json,sys
try: print(json.load(sys.stdin).get(sys.argv[1], ""))
except ValueError: pass' "$1"; }

check_url "backend /docs" "$BACKEND/docs"
check_url "desktop-backend /health" "$DESKTOP_BACKEND/health"

custom_token=$(curl -fsS --max-time 20 -X POST -F "uid=$UID_LOCAL" "$BACKEND/v1/auth/local-dev/custom-token" | json_field custom_token) || true
if [ -n "$custom_token" ]; then pass "custom token for $UID_LOCAL"; else fail "custom token"; fi

id_token=$(curl -fsS --max-time 10 -H 'Content-Type: application/json' \
  -d "{\"token\":\"$custom_token\",\"returnSecureToken\":true}" \
  "$AUTH_EMULATOR/identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=$FIREBASE_API_KEY" \
  | json_field idToken) || true
if [ -n "$id_token" ]; then pass "ID token from the Auth emulator"; else fail "ID token"; fi

# A fresh user has no profile document (GET /v1/users/profile answers 410),
# so check auth on a list the client reads right after sign-in.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BACKEND/v3/memories?limit=1")
if [ "$code" = 401 ]; then pass "GET /v3/memories without a token: 401"; else fail "GET /v3/memories without a token: $code, want 401"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "Authorization: Bearer $id_token" "$BACKEND/v3/memories?limit=1")
if [ "$code" = 200 ]; then pass "GET /v3/memories with the ID token"; else fail "GET /v3/memories with the ID token: $code"; fi

if [ "$paid" = 1 ]; then
  echo "paid: streaming fixtures/sample.wav to /v4/listen"
  # A one-off backend container: it is on the compose network and already has
  # websockets, so the host needs nothing extra.
  if docker compose run --rm --no-deps -T \
    -v "$PWD/smoke_listen.py:/smoke/smoke_listen.py:ro" \
    -v "$PWD/fixtures/sample.wav:/smoke/sample.wav:ro" \
    --entrypoint python backend /smoke/smoke_listen.py /smoke/sample.wav ru; then
    pass "conversation from sample.wav"
  else
    fail "conversation from sample.wav"
  fi
fi

exit "$failed"
