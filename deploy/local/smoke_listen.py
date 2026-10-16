"""Paid smoke step: stream a WAV into /v4/listen the way the desktop client
does and wait for the finished conversation.

Runs inside a one-off backend container on the compose network (smoke.sh
--paid), so the host needs nothing but Docker. Checks the transcript and the
summary; action items are only printed, see SPEC open question 7. Costs one Deepgram stream of
the file's length plus the OpenAI calls that process one conversation.
"""

import asyncio
import json
import sys
import time
import urllib.parse
import urllib.request
import wave

import websockets

BACKEND = 'http://backend:8080'
AUTH_EMULATOR = 'http://firebase:9099'
UID = 'local-dev-user'
CHUNK_SECONDS = 0.1
PROCESS_TIMEOUT_SECONDS = 180


def _post_form(url: str, form: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(form).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, method='POST'), timeout=20) as r:
        return json.load(r)


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(request, timeout=20) as r:
        return json.load(r)


def _patch_json(url: str, token: str, payload: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='PATCH',
    )
    urllib.request.urlopen(request, timeout=20).close()


def _get_json(url: str, token: str):
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=20) as r:
        return json.load(r)


def sign_in() -> str:
    custom = _post_form(f'{BACKEND}/v1/auth/local-dev/custom-token', {'uid': UID})['custom_token']
    signed = _post_json(
        f'{AUTH_EMULATOR}/identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=local',
        {'token': custom, 'returnSecureToken': True},
    )
    return signed['idToken']


def read_pcm16(path: str) -> tuple[bytes, int]:
    with wave.open(path) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            sys.exit(f'{path}: need mono 16-bit PCM')
        return w.readframes(w.getnframes()), w.getframerate()


async def stream(token: str, pcm: bytes, rate: int, language: str) -> tuple[str | None, list[str]]:
    # Same query and headers as buildListenEndpoint/buildListenHeaders in
    # desktop/windows/src/main/ipc/omiListen.ts.
    query = urllib.parse.urlencode(
        {
            'language': language,
            'sample_rate': rate,
            'codec': 'pcm16',
            'channels': 1,
            'include_speech_profile': 'false',
            'source': 'desktop',
            # Attributes the microphone speaker to the user; without it nothing
            # is "said by the user", so no action items or memories come out.
            'speaker_auto_assign': 'enabled',
        }
    )
    conversation_id = None
    texts: list[str] = []
    headers = {'Authorization': f'Bearer {token}', 'X-App-Platform': 'windows'}
    async with websockets.connect(f'ws://backend:8080/v4/listen?{query}', extra_headers=headers) as ws:

        async def receive() -> None:
            nonlocal conversation_id
            async for message in ws:
                if isinstance(message, bytes):
                    continue
                try:
                    data = json.loads(message)
                except ValueError:
                    continue  # keepalive text such as "ping"
                if isinstance(data, list):
                    texts.extend(segment.get('text', '') for segment in data)
                elif isinstance(data, dict) and data.get('type') == 'conversation_session':
                    conversation_id = data.get('conversation_id')

        receiver = asyncio.create_task(receive())
        chunk = int(rate * 2 * CHUNK_SECONDS)
        for start in range(0, len(pcm), chunk):
            await ws.send(pcm[start : start + chunk])
            await asyncio.sleep(CHUNK_SECONDS)
        # The client sends this on stop so Deepgram flushes the trailing words.
        await ws.send('finalize')
        await asyncio.sleep(5)
        await ws.close(code=1000)
        await asyncio.wait_for(receiver, timeout=10)
    return conversation_id, texts


def wait_for_conversation(token: str, conversation_id: str) -> dict:
    deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
    status = None
    while time.monotonic() < deadline:
        conversation = _get_json(f'{BACKEND}/v1/conversations/{conversation_id}', token)
        status = conversation.get('status')
        if status == 'completed':
            return conversation
        time.sleep(3)
    sys.exit(f'FAIL  conversation {conversation_id} still {status!r} after {PROCESS_TIMEOUT_SECONDS}s')


def main() -> None:
    path = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else 'ru'
    pcm, rate = read_pcm16(path)
    token = sign_in()
    # /v4/listen rejects a uid without a users/{uid} document ("Bad user"). The
    # client creates it on start by syncing the language; do the same.
    _patch_json(f'{BACKEND}/v1/users/language', token, {'language': language})
    conversation_id, texts = asyncio.run(stream(token, pcm, rate, language))
    if not conversation_id:
        sys.exit('FAIL  no conversation_session from /v4/listen')
    live = ' '.join(t for t in texts if t).strip()
    print(f'{"ok  " if live else "FAIL"}  live transcript: {live[:200]!r}')

    conversation = wait_for_conversation(token, conversation_id)
    structured = conversation.get('structured') or {}
    segments = conversation.get('transcript_segments') or []
    action_items = structured.get('action_items') or []
    checks = [
        (bool(segments), f'transcript: {len(segments)} segments'),
        (bool(structured.get('overview')), f'summary: {structured.get("title", "")!r}'),
    ]
    for ok, label in checks:
        print(f'{"ok  " if ok else "FAIL"}  {label}')
    # Not a failure: action items come only from speech attributed to the user,
    # and the local stack has no speaker identification (SPEC open question 7).
    print(f'info  action items: {[item.get("description") for item in action_items]}')
    if not live or not all(ok for ok, _ in checks):
        sys.exit(1)


if __name__ == '__main__':
    main()
