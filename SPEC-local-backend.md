# Спецификация: локальный бэкенд

Модуль `local-backend` из `CAPABILITY-MAP.md`. Зависит от `linux-run` и `llm-openrouter`.

Статус: черновик, на утверждении. Обновлено: 2026-10-16.

## Цель

Omi работает у меня на машине целиком: бэкенд в Docker, клиент `desktop/windows` ходит только в него. В контур Omi не уходит ничего: ни экран, ни звук, ни расшифровки, ни аналитика. Наружу ходят только провайдеры, которых я выбрал: OpenRouter и Deepgram, а прямые ключи OpenAI и Gemini — только для того, чего OpenRouter не умеет (карта функций в `SPEC-llm-openrouter.md`).

Вторая цель — скорость. Сейчас каждый запрос к `api.omi.me` тратит около 3,5 с только на соединение. Локально запросы к API должны проходить за доли секунды.

Пользователь один — я. Сервер для МКСКОМ и российские провайдеры — следующий модуль, `ru-backend`.

### Пользовательские сценарии

1. На машине есть только Docker. Выполняю `docker compose up -d` в `deploy/local`, через несколько минут все сервисы здоровы.
2. Запускаю клиент в локальном режиме, нажимаю «Войти локально». Приложение открывается с пустой базой, без входа через Google.
3. Пишу в чат — получаю ответ.
4. Записываю разговор с микрофона. После остановки появляется разговор с расшифровкой, сводкой и задачами.
5. Перезапускаю компьютер, поднимаю compose — разговоры, память и задачи на месте.
6. Работаю полдня. В журнале исходящих запросов нет ни одного обращения к доменам Omi.

### Что уже есть в репо

- `make dev-up` поднимает почти тот же набор, но без Docker и без `pusher`: эмуляторы Firestore и Auth, Redis, Typesense, `backend`, `llm-gateway`, `desktop-backend` (`scripts/dev-harness/dev_harness/cli.py:820`). Его `config.py` — источник переменных окружения для compose.
- Данные эмулятора стенд сохраняет через `--import` и `--export-on-exit`. Файлы вместо GCS — через `OMI_LOCAL_STORAGE_ROOT`.
- В бэкенде есть вход для Auth-эмулятора: `POST /v1/auth/local-dev/custom-token` (`backend/routers/auth.py:1276`). Он существует, только если задан `FIREBASE_AUTH_EMULATOR_HOST`.
- Образы: `backend/Dockerfile`, `backend/Dockerfile.desktop_backend`, `backend/pusher/Dockerfile`. Базовый образ по умолчанию лежит в реестре Omi (`gcr.io/based-hardware-dev/...`), его подменяем на `python:3.11-slim`.

## Решения

- **Данные:** старт с пустой базы. Перенос из облака Omi — отдельная задача.
- **Вход:** Auth-эмулятор и `local-dev/custom-token`, без Google. Проект Firebase — `demo-omi-local`, как у стенда.
- **Модели:** по правилам `llm-openrouter`.
- **Речь:** Deepgram, включая разметку говорящих.
- **ML-сервисы без видеокарты:**
  - VAD отдельным сервисом не нужен: без `HOSTED_VAD_API_URL` бэкенд сам запускает ту же модель Silero на процессоре (`utils/stt/vad.py`).
  - `diarizer` в первую версию не входит. Deepgram делит речь на «говорящий 1», «говорящий 2», но имена по голосу и профиль своего голоса не работают (`utils/stt/speaker_embedding.py`). После запуска оцениваем, насколько не хватает имен, и добавляем его отдельной задачей: он на `pyannote-audio` и умеет работать на процессоре.
  - `parakeet` не нужен: распознавание речи делает Deepgram, а для `parakeet` нужна видеокарта NVIDIA.
  - NLLB не нужен: перевода расшифровок нет. Если понадобится, переводить через LLM.
- **Не работают и не чиним:** оплата и Stripe, магазин приложений, интеграции через OAuth (Google Календарь, Notion и другие), публичные ссылки на разговоры, Pinecone (смысловой поиск по разговорам; поиск по словам через Typesense работает).

## Состав compose

| Сервис | Образ | Порт на `127.0.0.1` | Данные |
|---|---|---|---|
| `firebase` | свой: Node 22, OpenJDK 21, `firebase-tools` той же версии, что в корневом `package.json`; Firestore и Auth | 8085, 9099 | volume `emulator-data` |
| `redis` | `redis:7` | — | — |
| `typesense` | `typesense/typesense:27.1` | — | volume `typesense-data` |
| `backend` | `backend/Dockerfile` | 8000 | volume `storage` |
| `pusher` | `backend/pusher/Dockerfile` | — | — |
| `llm-gateway` | образ `backend`, команда `uvicorn llm_gateway.main:app` (своего Dockerfile у шлюза нет) | — | — |
| `desktop-backend` | `backend/Dockerfile.desktop_backend` | 10201 | — |

Порты те же, что у стенда `make dev-up`. Наружу открыты только порты, которые нужны клиенту, и только на `127.0.0.1`. Все образы собираются из корня репо.

Что выяснилось про запуск:
- Эмуляторы в контейнере должны слушать `0.0.0.0`, иначе другие контейнеры до них не достучатся. В `firebase.json` стенда стоит `127.0.0.1`.
- Файловое хранилище вместо GCS (`utils/other/local_storage.py:30`) включается, только если задан `OMI_HARNESS_STATE_ROOT`, проект начинается с `demo-`, задан `FIRESTORE_EMULATOR_HOST`, а `OMI_LOCAL_STORAGE_ROOT` лежит внутри корня состояния.
- `pusher` не стартует без `MEMORY_ENABLED=on` (`pusher/main.py:37`). Бэкенд находит его по `HOSTED_PUSHER_API_URL=http://pusher:8080`.
- `OMI_LLM_GATEWAY_FEATURE_MODE=gateway` разрешен только при `OMI_ENV_STAGE=local` (или `dev`, `test`).
- Переменные окружения переносим из `_harness_service_extra` и `child_env_for` стенда (`scripts/dev-harness/dev_harness/config.py:357-448`).

## Изменения в клиенте

Все изменения включаются только в локальном режиме. Без него клиент работает как сейчас.

1. **Профиль настроек** `desktop/windows/.env.local-backend.example`: адреса `http://127.0.0.1:8000` и `http://127.0.0.1:10201`, проект `demo-omi-local`, `VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099`, пустой ключ PostHog. Запуск: `npx pnpm@10 dev --mode local-backend`. Имя режима не `local`: файл `.env.local` Vite читает в любом режиме.
2. **CSP и CORS.** `connect-src` во всех четырех HTML-входах (`renderer/index.html`, `capture.html`, `glow.html`, `insight-toast.html`) пропускает локальные адреса, включая `ws://` и Auth-эмулятор. Список `apiUrls` для подмены CORS в `src/main/index.ts:711` включает адреса из профиля.
3. **Адрес записи и транскрипции** (`src/main/ipc/omiListen.ts:75,83`) строится из `VITE_OMI_API_BASE`, а не зашит.
4. **Аналитика** (`renderer/src/lib/analytics.ts:11`): без ключа выключена, зашитого ключа нет. Ссылки на разговоры (`renderer/src/lib/shareLinks.ts`) не ведут на `h.omi.me`.
5. **Вход:** при заданном `VITE_FIREBASE_AUTH_EMULATOR_HOST` клиент подключается к эмулятору (`connectAuthEmulator` после создания `auth` в `renderer/src/lib/firebase.ts`) и показывает на `renderer/src/pages/Login.tsx` кнопку «Войти локально»: `POST /v1/auth/local-dev/custom-token`, затем `signInWithCustomToken`.
6. **Проверка токена в main-процессе** (`src/main/auth/firebaseIdToken.ts`, единственный вызов — `src/main/ipc/pimono.ts:45`). Эмулятор выдает неподписанные токены, и нынешняя проверка их отвергнет. Тогда чат на `pi_mono` не заработает. В режиме эмулятора принимаем токены эмулятора с проверкой `iss`, `aud` и срока. Режим задается при сборке, в обычной сборке такие токены отвергаются.
7. **Расширение pi-mono** получает `OMI_API_BASE_URL` из профиля, а не `https://api.omi.me/v2` по умолчанию (`src/main/codingAgent/pi-mono-extension/index.ts:1030`).
8. **Ограничение исходящих запросов** в main-процессе через `session.webRequest`: разрешены `127.0.0.1` и хосты из явного списка. Остальное блокируется и пишется в журнал `[egress]`. Запросы через `fetch` из main-процесса идут мимо `session`. Их адреса уже собраны: из профиля берутся `ipc/auth.ts`, `ipc/byok.ts`, `ipc/mcpExports.ts`, `ipc/memoryCleanup.ts`. Прямые обращения к провайдерам (`agentKernel/byokValidator.ts`, голосовой режим в `renderer/src/lib/voice/hub/`) происходят только с вашими ключами BYOK.

Проверка обновлений (`src/main/updater.ts`) работает только на Windows, на Linux ее менять не нужно. Sentry без DSN выключен, а DSN в `.env` нет.

## Стек

Docker Compose v2. Бэкенд — код Omi на Python 3.11 без переписывания. Клиент — Electron, TypeScript, `npx pnpm@10`. Новых npm- и Python-зависимостей нет.

## Команды

```bash
# бэкенд, из deploy/local
./init.sh                          # создает .env: случайные секреты, спрашивает ключи OpenRouter и Deepgram
docker compose up -d --build
docker compose ps                  # все сервисы healthy
docker compose logs -f backend
./smoke.sh                         # проверка: здоровье сервисов, вход, чат, запись из файла
docker compose down                # данные остаются в volume

# клиент, из desktop/windows
cp .env.local-backend.example .env.local-backend
npx pnpm@10 dev --mode local-backend
npx pnpm@10 exec vitest run src/main/auth src/main/ipc src/renderer/src/lib
npx pnpm@10 typecheck
npx pnpm@10 lint
```

## Структура

```
deploy/local/
  compose.yaml                 сервисы, volume, healthcheck
  firebase/Dockerfile          эмуляторы Firestore и Auth
  firebase/firebase.json       хосты 0.0.0.0, порты, rules и indexes из корня репо
  .env.example                 все переменные с комментариями, без значений секретов
  init.sh                      создание .env
  smoke.sh                     проверка стека
  README.md                    запуск с нуля, ключи, сброс данных
desktop/windows/
  .env.local-backend.example
  src/main/index.ts            CORS для локальных адресов, подключение egressGuard
  src/main/ipc/omiListen.ts
  src/main/auth/firebaseIdToken.ts
  src/main/codingAgent/pi-mono-extension/index.ts
  src/main/egressGuard.ts      новый: список разрешенных хостов и журнал
  src/renderer/index.html, capture.html, glow.html, insight-toast.html
  src/renderer/src/lib/analytics.ts, firebase.ts, shareLinks.ts
  src/renderer/src/pages/Login.tsx
  changelog/unreleased/2026-10-local-backend.json
```

`deploy/local/.env` в `.gitignore`.

## Стиль кода

В compose — явные `healthcheck` и `depends_on: condition: service_healthy`, без `latest` в тегах образов. В клиенте — как в соседних файлах: решения в чистых функциях, ввод-вывод в тонкой обертке.

```ts
// Local-backend mode: the renderer may only reach hosts the operator listed.
// Pure so the allowlist is unit-testable without Electron.
export function isEgressAllowed(url: string, allowed: readonly string[]): boolean {
  let host: string
  try {
    host = new URL(url).hostname
  } catch {
    return false
  }
  if (host === '127.0.0.1' || host === 'localhost') return true
  return allowed.some((h) => host === h || host.endsWith(`.${h}`))
}
```

## Тестирование

- **Юнит-тесты клиента (vitest):**
  - адрес записи строится из базового адреса, `https` становится `wss`, `http` — `ws`;
  - аналитика без ключа не инициализируется;
  - `isEgressAllowed`: localhost, разрешенный хост, поддомен, чужой хост, мусор вместо URL;
  - проверка токена: обычная сборка отвергает неподписанный токен (тест безопасности), режим эмулятора принимает токен эмулятора с верными `iss` и `aud` и отвергает с чужими.
- **`smoke.sh`:** здоровье всех сервисов, вход через `local-dev/custom-token`, `GET` профиля, один ответ чата, разговор из короткого WAV-файла через Deepgram. Чат и Deepgram стоят денег, поэтому это отдельный флаг `--paid`.
- **Ручная проверка** по сценариям 1–6.
- **Исходящие запросы бэкенда:** на время проверки контейнеры ходят наружу через прокси с журналом (`HTTPS_PROXY`). В журнале должны быть только разрешенные хосты.

## Границы

- **Всегда:** включать изменения клиента только в локальном режиме; хранить секреты только в `deploy/local/.env`; публиковать порты только на `127.0.0.1`; запускать тесты, `typecheck` и `lint` перед коммитом.
- **Сначала спросить:** правки кода бэкенда, кроме того, что описано в `llm-openrouter`; новые зависимости; реальные платные вызовы; изменения поведения клиента вне локального режима; пуш в `origin`.
- **Никогда:** коммитить ключи и `.env`; тянуть образы из `gcr.io/based-hardware*`; отключать проверку токена в обычной сборке; отправлять данные в контур Omi ради проверки.

## Критерии готовности

1. С чистой машины, где есть только Docker, по `deploy/local/README.md` стек поднимается и клиент входит локально за 30 минут.
2. `docker compose ps`: все 7 сервисов в состоянии `healthy`.
3. Сценарии 1–6 проходят вручную.
4. За 4 часа работы в журнале `[egress]` клиента и в журнале прокси бэкенда нет обращений к `*.omi.me`, `*.omiapi.com`, `*.run.app`, `posthog.com`, `based-hardware*.firebaseapp.com`.
5. После `docker compose down` и `up` разговоры, память и задачи на месте.
6. Список разговоров открывается быстрее 300 мс (медиана `GET /v1/conversations`, сейчас около 4 с).
7. Без локального режима клиент ведет себя как раньше: существующие тесты зеленые.

## Открытые вопросы

1. **Сохраняет ли эмулятор данные при `docker compose down`.** `--export-on-exit` срабатывает при корректной остановке. Проверить сигнал и `stop_grace_period`; если ненадежно, добавить периодический экспорт.
2. **Память эмулятора** при нескольких месяцах данных: эмулятор держит все в памяти. Замерить на этапе проверки.
3. **Распознавание через Deepgram в `pusher` и бэкенде.** Какое значение `STT_SERVICE_MODELS` выбирает Deepgram. Стенд в офлайн-режиме ставит `parakeet`, со значением `soniox` без ключа сервис не стартует.
4. **Голосовой режим и проверка ключей BYOK** ходят к провайдерам напрямую из клиента. Решить, включать ли их хосты в список разрешенных или оставить заблокированными.
5. **`diarizer` на процессоре.** Проверить, что запись и сводка без него не ломаются. Для задачи с `diarizer`: нужен ли токен HuggingFace для моделей `pyannote`, сколько весит образ и сколько времени уходит на минуту записи на процессоре.
6. **Прокси для проверки исходящих запросов бэкенда:** какой взять (`tinyproxy`, `squid`) и держать ли его в compose постоянно.
