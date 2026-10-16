# Omi Plugins

Reference material for building Omi apps: services that run outside the backend and
plug into it through webhooks, chat tools and OAuth. The platform side (app store,
webhook delivery, chat tools, MCP) lives in `backend/`; how to write an app is in
`docs/doc/developer/apps/`.

## `omi-plugin-sdk/` — webhook payload models

A small Python package with the Omi webhook payload models (`omi_plugin_sdk.models`:
`Conversation`, `TranscriptSegment`, `ActionItem`, ...). It is models-only. The backend
imports it from `plugins/omi-plugin-sdk/src` when present and falls back to built-in
copies otherwise. Tests: `scripts/run-plugin-sdk-tests.sh`.

## Example apps

Each is a self-contained FastAPI service with its own `main.py`, `requirements.txt` and
deploy descriptor (Procfile / railway.toml; GitHub also has a Dockerfile):

- `omi-dropbox-app/` — conversation webhook (`POST /conversation`): saves each finished
  conversation's summary, transcript and audio to Dropbox after an OAuth setup.
- `omi-notion-app/` — OAuth plus chat tools that search, read and write Notion pages.
- `omi-github-app/` — chat tools that create and manage GitHub issues.
- `omi-google-calendar-app/` — OAuth plus chat tools for Google Calendar events.

Chat-tool apps publish their tool list at `/.well-known/omi-tools.json`.

The other upstream examples (Slack, Linear, Whoop, Shopify and more) are in
BasedHardware/omi under `plugins/`.

`scripts/check_plugin_request_timeouts.py` fails any `requests` call in `plugins/`
that has no timeout.
