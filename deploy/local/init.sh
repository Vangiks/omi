#!/usr/bin/env bash
# Creates .env from .env.example: random secrets plus the provider keys you
# enter. Leaves an existing .env alone, because a new ENCRYPTION_SECRET would
# make the stored data unreadable.
set -euo pipefail
cd "$(dirname "$0")"

if [ -e .env ]; then
  echo ".env already exists; edit it by hand or remove it first." >&2
  exit 1
fi

secret() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

declare -A values=(
  [ENCRYPTION_SECRET]=$(secret)
  [ADMIN_KEY]=$(secret)
  [OMI_LLM_GATEWAY_SERVICE_TOKEN]=$(secret)
  [TYPESENSE_API_KEY]=$(secret)
  [SCREEN_FRAME_SIGNING_SECRET]=$(secret)
)

if [ -t 0 ]; then
  echo "Provider keys; press Enter to skip and add them to .env later."
  for key in OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY PERPLEXITY_API_KEY DEEPGRAM_API_KEY; do
    read -rsp "$key: " value
    echo
    values[$key]=$value
  done
fi

umask 077
while IFS= read -r line; do
  key=${line%%=*}
  if [[ $line =~ ^[A-Z_]+=$ && -n ${values[$key]:-} ]]; then
    printf '%s=%s\n' "$key" "${values[$key]}"
  else
    printf '%s\n' "$line"
  fi
done < .env.example > .env

echo "Created $(pwd)/.env"
