<div align="center">

# **omi**

### A 2nd brain you trust more than your 1st

Omi captures your screen and conversations, transcribes in real-time, generates summaries and action items, and gives you an AI chat that remembers everything you've seen and heard. Works on desktop, phone and wearables. Fully open source.

Trusted by 300,000+ professionals.


[![Discord](https://img.shields.io/discord/1192313062041067520?label=Discord&logo=discord&logoColor=white&style=for-the-badge)](http://discord.omi.me)&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Omi?style=for-the-badge)](https://github.com/BasedHardware/Omi)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Website](https://omi.me/) · [Docs](https://docs.omi.me/) · [Discord](http://discord.omi.me) · [Twitter](https://x.com/kodjima33) · [DeepWiki](https://deepwiki.com/BasedHardware/omi)

</div>

> **This fork** ([Vangiks/omi](https://github.com/Vangiks/omi)) keeps the Electron desktop app
> (`desktop/windows`, developed on Linux), `web/` and the backend, which runs locally in Docker
> (`deploy/local`). The mobile app, firmware, Omi Glass and device SDKs were removed;
> `desktop/macos` stays for reference.

## Quick Start

### macOS

```sh
git clone https://github.com/BasedHardware/omi.git && cd omi/desktop/macos && ./run.sh --yolo
```

Builds the macOS app, connects to the cloud backend, and launches. No env files, no credentials, no local backend.

> **Requirements:** macOS 14+, [Xcode](https://developer.apple.com/xcode/) (includes Swift & code signing), [Node.js](https://nodejs.org/)

### Desktop app (Linux, Windows)

```sh
cd desktop/windows
cp .env.example .env
npx pnpm@10 install --frozen-lockfile
npx pnpm@10 run dev
```

Use `npx pnpm@10`, not `npm install`: the system pnpm and npm break the hoisted layout. Linux runtime
packages and Wayland notes are in [`desktop/windows/LINUX.md`](desktop/windows/LINUX.md).

### Local backend

```sh
cd deploy/local
./init.sh
docker compose up -d --build --wait
```

See [`deploy/local/README.md`](deploy/local/README.md).

For backend development outside Docker, `make setup` syncs the pinned backend Python environment.

<details>
  <summary>Full Installation</summary>
  
For local development with the full backend stack:

1. Install prerequisites

```bash
xcode-select --install
uv --version
```

2. Clone and configure

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/desktop/macos
cp ../../backend/.env.example ../../backend/.env
```

3. Build and run

```bash
./run.sh
```

See [desktop/macos/README.md](desktop/macos/README.md) for environment variables and credential setup.


</details>

<p align="center">
  <a href="https://macos.omi.me"><img src="docs/assets/readme/download-macos-badge.png" alt="Download for macOS" height="50"></a>
</p>

<p align="center">
  <a href="https://app.omi.me">Try in Browser</a>
</p>

<details>
  <summary>How it works</summary>


```
┌─────────────────────────────────────────────────────────┐
│                      Your Devices                       │
│                                                         │
│  ┌───────────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Desktop App       │  │ macOS App    │  │ Web App  │  │
│  │ (Electron)        │  │ (Swift)      │  │ (Next.js)│  │
│  └─────────┬─────────┘  └──────┬───────┘  └────┬─────┘  │
│            │      HTTPS/WS     │               │        │
└────────────┼───────────────────┼───────────────┼────────┘
             │                   │               │
             ▼                   ▼               ▼
┌─────────────────────────────────────────────────────────┐
│                    Omi Backend (Python)                  │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │ Listen  │  │ Pusher   │  │ VAD     │  │ Diarizer │  │
│  │ (REST)  │  │ (WS)     │  │ (GPU)   │  │ (GPU)    │  │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘  │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │ Deepgram│  │ Firestore│  │ Redis   │  │ LLMs     │  │
│  │ (STT)   │  │ (DB)     │  │ (Cache) │  │ (AI)     │  │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

| Component | Path | Stack |
|-----------|------|-------|
| **Desktop app** | [`desktop/windows/`](desktop/windows/) | Electron, React, TypeScript (Windows, Linux) |
| macOS app (reference) | [`desktop/macos/`](desktop/macos/) | Swift, SwiftUI, Python desktop backend |
| Web | [`web/`](web/) | Next.js: user app, admin, public share pages |
| Backend API | [`backend/`](backend/) | Python, FastAPI, Firebase |
| Local backend | [`deploy/local/`](deploy/local/) | Docker Compose, Firebase emulators |
| Plugins | [`plugins/`](plugins/) | Plugin SDK and example apps |
| CLI | [`sdks/python-cli/`](sdks/python-cli/) | `omi` command-line client |

</details>

## Documentation

### Getting Started
- [Introduction](https://docs.omi.me/)
- [Quick Start Guide](https://docs.omi.me/quickstart)
- [macOS App Development](desktop/macos/README.md)
- [Backend Setup](https://docs.omi.me/doc/developer/backend/Backend_Setup)
- [Product behavior](PRODUCT.md)

### Building Apps
- [App Development Guide](https://docs.omi.me/doc/developer/apps/Introduction)
- [Example Apps](https://docs.omi.me/doc/developer/apps/examples/Github) — GitHub, Slack, OmiMentor
- [Audio Streaming Apps](https://docs.omi.me/doc/developer/apps/AudioStreaming)
- [Custom Chat Tools](https://docs.omi.me/doc/developer/apps/ChatTools)
- [Submit to App Store](https://docs.omi.me/doc/developer/apps/Submitting)

### API & SDKs
- [API Reference](https://docs.omi.me/api-reference/introduction) — REST endpoints for memories, conversations, action items

### Architecture
- [Backend Deep Dive](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- [Transcription Pipeline](https://docs.omi.me/doc/developer/backend/transcription)
- [Chat System](https://docs.omi.me/doc/developer/backend/chat_system)
- [Audio Streaming Pipeline](https://docs.omi.me/doc/developer/backend/backend_deepdive)

## License

MIT — see [LICENSE](LICENSE)
