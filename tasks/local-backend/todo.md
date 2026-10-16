# Задачи: локальный бэкенд

План и обоснования: `tasks/local-backend/plan.md`.

Обозначения проверок:
- `compose` = `docker compose -f deploy/local/docker-compose.yaml` (из корня репо)
- `smoke` = `deploy/local/smoke.sh`
- `vitest:X` = `npx pnpm@10 exec vitest run X` (из `desktop/windows`)
- `checks` = `npx pnpm@10 typecheck && npx pnpm@10 lint` (из `desktop/windows`)
- `app` = `npx pnpm@10 dev --mode local-backend` (из `desktop/windows`)

---

## Этап 1: бэкенд в Docker

### T1. Эмуляторы Firebase в контейнере

**Что сделать:** образ с Node 22, OpenJDK 21 и `firebase-tools` той же версии, что в корневом `package.json`. Свой `firebase.json` с хостами `0.0.0.0`, правилами и индексами из корня репо. В compose пока один сервис `firebase` с volume для данных и `--import`/`--export-on-exit`.

**Готово, когда:**
- [x] `compose up -d firebase` поднимает Firestore на 8085 и Auth на 9099 только на `127.0.0.1`
- [x] документ, записанный через REST эмулятора, остается после `compose down` и `compose up`
- [x] в README записано, как ведут себя данные при `compose down`, `compose stop`, перезагрузке и `kill`

**Проверка:** запись документа `curl`-ом, перезапуск, чтение

**Зависит от:** —

**Файлы:** `deploy/local/firebase/Dockerfile`, `deploy/local/firebase/firebase.json`, `deploy/local/docker-compose.yaml`, `deploy/local/README.md`

**Размер:** M

---

### T2. Бэкенд, шлюз и desktop-backend

**Что сделать:** в compose добавить `redis`, `typesense`, `backend`, `llm-gateway`, `desktop-backend` с базовым образом `python:3.11-slim`. `.env.example` с переменными из `_harness_service_extra` стенда (адреса контейнеров, файловое хранилище, бакеты, `OMI_ENV_STAGE=local`, `OMI_LLM_GATEWAY_FEATURE_MODE=gateway`). `init.sh` создает `.env` со случайными секретами и спрашивает ключи. `smoke.sh` без платных шагов.

**Готово, когда:**
- [x] `compose ps`: шесть сервисов `healthy`; порты 8000 и 10201 открыты только на `127.0.0.1`
- [x] `smoke` проходит: `/docs` у бэкенда и `desktop-backend`, `POST /v1/auth/local-dev/custom-token`, обмен на ID-токен в Auth-эмуляторе, `GET /v3/memories` с этим токеном (200) и без него (401). Профиль не подходит: у нового пользователя `GET /v1/users/profile` отвечает 410
- [x] `deploy/local/.env` в `.gitignore`; в репо нет ключей

**Проверка:** `compose up -d --build && compose ps && smoke`

**Зависит от:** T1

**Файлы:** `deploy/local/docker-compose.yaml`, `deploy/local/.env.example`, `deploy/local/init.sh`, `deploy/local/smoke.sh`, `.gitignore`

**Размер:** M

---

### T3. pusher и Deepgram

**Что сделать:** выяснить по `backend/utils/stt/streaming.py` и `backend/config/stt_provider_policy.py`, какие настройки выбирают Deepgram. Добавить `pusher` (`MEMORY_ENABLED=on`, `HOSTED_PUSHER_API_URL=http://pusher:8080`). В `smoke.sh --paid` — потоковая отправка короткого WAV в `/v4/listen` по образцу `backend/testing/listen_pusher_stack/`.

**Готово, когда:**
- [x] `compose ps`: семь сервисов `healthy`
- [x] `smoke --paid`: после отправки WAV появляется разговор в статусе `completed` с расшифровкой и сводкой. Задач нет: без определения спикеров они не извлекаются, решено не делать в этом модуле (открытый вопрос 7)
- [x] ответ на открытый вопрос 3 записан в спеку

**Проверка:** `smoke --paid` (только с разрешения; нужны прямые ключи моделей)

**Зависит от:** T2

**Файлы:** `deploy/local/docker-compose.yaml`, `deploy/local/.env.example`, `deploy/local/smoke.sh`, `deploy/local/fixtures/sample.wav`, `SPEC-local-backend.md`

**Размер:** M

---

### Контрольная точка A: бэкенд без клиента

- [x] T1–T3 выполнены, `smoke` и `smoke --paid` проходят
- [x] данные переживают перезапуск compose (7 разговоров до и после `down`/`up`)
- [x] обсудить, прежде чем переключать клиент: голосовой ввод и распознавание файлов откладываем, `DREAM_AGENT` оставляем включенным

---

## Этап 2: клиент

### T4. Профиль и доступ к локальным адресам

**Что сделать:** `desktop/windows/.env.local-backend.example`. В `connect-src` четырех HTML-входов добавить локальные адреса (`http` и `ws` для 8000, `http` для 10201 и 9099). Список CORS в `src/main/index.ts:711` дополнить адресами из профиля.

**Готово, когда:**
- [x] `app` запускается, в консоли окон нет нарушений CSP при запросе к `http://127.0.0.1:8000`
- [x] без профиля HTML и CORS для облака работают как раньше

**Проверка:** `checks`; запуск `app`, `fetch('http://127.0.0.1:8000/docs')` из консоли главного окна

**Зависит от:** T2

**Файлы:** `desktop/windows/.env.local-backend.example`, `src/renderer/index.html`, `src/renderer/capture.html`, `src/renderer/glow.html`, `src/renderer/insight-toast.html`, `src/main/index.ts`

**Размер:** M (правки однотипные)

---

### T5. Вход через эмулятор

**Что сделать:** в `src/renderer/src/lib/firebase.ts` при заданном `VITE_FIREBASE_AUTH_EMULATOR_HOST` вызвать `connectAuthEmulator`. На `src/renderer/src/pages/Login.tsx` в этом режиме показать кнопку «Войти локально»: `POST /v1/auth/local-dev/custom-token`, затем `signInWithCustomToken`.

**Готово, когда:**
- [x] в режиме `local-backend` вход по кнопке открывает приложение с пустой базой; пользователь появился в Auth-эмуляторе
- [x] без переменной эмулятора кнопки нет, вход через Google и Apple не изменился

**Проверка:** `vitest:src/renderer/src/pages`, `checks`, ручной вход в `app`

**Зависит от:** T4

**Файлы:** `src/renderer/src/lib/firebase.ts`, `src/renderer/src/pages/Login.tsx`, тест рядом с `Login.tsx`

**Размер:** S

---

### T6. Проверка токена эмулятора → чат

**Что сделать:** в `src/main/auth/firebaseIdToken.ts` ветка для режима эмулятора, заданного при сборке: принимать неподписанный токен эмулятора при верных `iss` (`https://securetoken.google.com/demo-omi-local`), `aud` и сроке.

**Готово, когда:**
- [x] тест безопасности: без режима эмулятора неподписанный токен отвергается (как сейчас)
- [x] в режиме эмулятора токен с верными `iss`, `aud`, сроком принимается, с чужими или просроченный — нет
- [x] в `app` чат отвечает (сценарий 3)

**Проверка:** `vitest:src/main/auth`, `checks`, сообщение в чат в `app`

**Зависит от:** T5; для ответа чата нужен LLM-ключ в бэкенде

**Файлы:** `src/main/auth/firebaseIdToken.ts`, `src/main/auth/firebaseIdToken.test.ts`

**Размер:** S

---

### T7. Адрес записи из профиля → запись разговора

**Что сделать:** `buildListenEndpoint` в `src/main/ipc/omiListen.ts` строит адрес из `VITE_OMI_API_BASE`: `https` → `wss`, `http` → `ws`, путь и параметры как сейчас.

**Готово, когда:**
- [x] тесты: облачный адрес дает те же URL, что сейчас; локальный — `ws://127.0.0.1:8000/v4/listen?...`
- [x] в `app` запись с микрофона дает разговор с расшифровкой и сводкой (сценарий 4; задач нет, открытый вопрос 7)

**Проверка:** `vitest:src/main/ipc`, `checks`, запись 1–2 минут в `app`

**Зависит от:** T3, T5

**Файлы:** `src/main/ipc/omiListen.ts`, тест к нему

**Размер:** S

---

### Контрольная точка B: напарник работает локально

- [ ] сценарии 2–5 из спеки проходят вручную
- [ ] `checks` и тесты клиента зеленые
- [ ] обсудить, прежде чем закрывать утечки

---

## Этап 3: приватность и проверка

### T8. Аналитика, ссылки, pi-mono

**Что сделать:** `analytics.ts` без зашитого ключа: пустой ключ — аналитика выключена. `shareLinks.ts` в режиме `local-backend` не строит ссылки на `h.omi.me`. Расширение pi-mono получает `OMI_API_BASE_URL` из профиля.

**Готово, когда:**
- [x] тесты: без ключа `trackEvent` ничего не отправляет; с ключом — как раньше
- [x] в режиме `local-backend` запросов к `posthog.com` и `h.omi.me` нет (ключа PostHog нет в сборке, ссылка на разговор не строится; журнал за 4 часа — в T10)
- [x] pi-mono в режиме `local-backend` ходит на локальный бэкенд. Код не менялся: `OMI_API_BASE_URL` уже строится из `VITE_OMI_DESKTOP_API_BASE` (`piMonoManagedApiBaseUrl`), то есть `http://127.0.0.1:10201/v2`, а не 8000; чат отвечал через `desktop-backend`

**Проверка:** `vitest:src/renderer/src/lib`, `checks`

**Зависит от:** T4

**Файлы:** `src/renderer/src/lib/analytics.ts`, `src/renderer/src/lib/shareLinks.ts`, место, где запускается расширение pi-mono в `src/main/codingAgent/`, тесты

**Размер:** M

---

### T9. Ограничение исходящих запросов клиента

> **Отложено 2026-10-16.** Решили не блокировать: известные утечки закрыты в T7 и T8, остальное смотрим в процессе работы. Ответ на открытый вопрос 4: голосовой режим bar (Gemini Live, OpenAI realtime) и проверка ключей BYOK ходят к провайдерам напрямую, это разрешено. Если понадобится гарантия, начинать с режима «только журнал `[egress]`», блокировку включать потом.

**Что сделать:** `src/main/egressGuard.ts` с чистой функцией `isEgressAllowed` и подключением к `session.webRequest` в режиме `local-backend`: разрешены `127.0.0.1` и хосты из списка в профиле, остальное блокируется и пишется в журнал `[egress]`. Решить открытый вопрос 4 спеки.

**Готово, когда:**
- [ ] тесты `isEgressAllowed`: localhost, разрешенный хост, поддомен, чужой хост, мусор вместо URL
- [ ] в `app` попытка запроса к `api.omi.me` блокируется и видна в журнале
- [ ] без профиля ограничение не включается

**Проверка:** `vitest:src/main/egressGuard.test.ts`, `checks`, ручная проверка в `app`

**Зависит от:** T4

**Файлы:** `src/main/egressGuard.ts`, `src/main/egressGuard.test.ts`, `src/main/index.ts`, `desktop/windows/.env.local-backend.example`

**Размер:** M

---

### T10. Проверка исходящих запросов бэкенда, замеры, документация

**Что сделать:** профиль compose `audit` с прокси, который пишет журнал соединений; контейнеры ходят наружу через него (`HTTPS_PROXY`). Полдня работы с журналами. Замер `GET /v1/conversations`. README с нуля до работающего приложения. Фрагмент changelog клиента.

**Готово, когда:**
- [ ] за 4 часа в журнале `[egress]` и в журнале прокси нет `*.omi.me`, `*.omiapi.com`, `*.run.app`, `posthog.com`, `based-hardware*` (критерий 4)
- [ ] медиана `GET /v1/conversations` меньше 300 мс (критерий 6)
- [ ] по README стек поднимается с чистой машины за 30 минут (критерий 1)
- [ ] память эмулятора записана в спеку (открытый вопрос 2)

**Проверка:** журналы, замер, прогон README

**Зависит от:** T7, T8, T9

**Файлы:** `deploy/local/docker-compose.yaml`, `deploy/local/README.md`, `desktop/windows/changelog/unreleased/2026-10-local-backend.json`, `SPEC-local-backend.md`

**Размер:** M

---

### Контрольная точка C: модуль готов

- [ ] критерии готовности 1–7 из спеки выполнены
- [ ] решить, нужна ли задача на `diarizer` на процессоре
- [ ] пуш в `origin` — только с моего разрешения
