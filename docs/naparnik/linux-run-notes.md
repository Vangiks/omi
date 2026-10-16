# Заметки по запуску Omi на Linux

Этап 1 (`linux-run`) задачи #8 «Определение созвона на Linux». Машина: Ubuntu 24.04, X11, PipeWire, Node 22.23.2, pnpm 10 через `npx pnpm@10`.

## Установка (2026-10-15)

- `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-rus` поставлены, `tesseract --list-langs` показывает `eng`, `osd`, `rus`.
- `pw-dump`, `xprop`, `pidstat` уже были в системе.
- `.env` скопирован из `.env.example`, он в `.gitignore`.
- `npx pnpm@10 install --frozen-lockfile`: пакеты встали, но `postinstall` упал на пересборке `better-sqlite3`. Тайм-аут соединения с `artifacts.electronjs.org`, откуда качаются заголовки Electron. Повторная полная установка висела на запросах к реестру npm больше 10 минут. Помог отдельный запуск `npx pnpm@10 run postinstall`: `better-sqlite3` пересобран, помощники для Windows (OCR, звук, автоматизация) на Linux пропускаются, проверки зависимостей проходят.
- Если сеть снова подведет, сначала запускать `npx pnpm@10 run postinstall`, а не всю установку.

## База проверок до наших изменений (2026-10-15)

Ветка `cleanup/non-code`. Код в `desktop/windows/src` совпадает с `origin/main`.

| Проверка | Результат |
|---|---|
| `typecheck` | чисто |
| `lint` | 0 ошибок, 932 предупреждения (почти все — форматирование Prettier, в CI не блокирует) |
| `test` | 560 файлов, 5615 тестов: 34 упали, 31 пропущен |
| `vitest run src/main/meeting src/main/usage` | 12 файлов, 84 теста, все зеленые |

Упавшие тесты по причинам:

1. **Русская локаль системы (`LANG=ru_RU.UTF-8`)**, 2 теста. Проходят с `LANG=en_US.UTF-8`: тесты ждут формат чисел `1,234`, а в русской локали выходит `1 234`.
   - `src/renderer/src/components/ui/DbRecoveryNotice.test.tsx` — «reports how many items were recovered after a successful salvage»
   - `src/renderer/src/components/apps/AppDetailSheet.test.tsx` — «shows rating (only with count) and installs in the header»
2. **Нестабильные тесты чата и онбординга**, от 4 до 30 падений за прогон, число каждый раз разное. Тесты завязаны на тайминги (`mainChatSend was never called`, тайм-ауты 5 с). С `.env` в каталоге и при параллельной нагрузке падает больше.
   - `src/renderer/src/hooks/useChat.pimono.test.tsx`
   - `src/renderer/src/hooks/useChat.persona.test.tsx`
   - `src/renderer/src/hooks/useChat.dispatch.test.tsx`
   - `src/renderer/src/components/onboarding/BuildProfileStep.test.tsx`

К модулю созвонов эти падения отношения не имеют. Для сравнения после изменений достаточно, чтобы `src/main/meeting` и `src/main/usage` оставались зелеными, а в полном прогоне не появились новые упавшие файлы, кроме перечисленных.

## Запуск и вход

2026-10-15: `npx pnpm@10 dev` запускается, вход своим аккаунтом Omi работает.

## Расшифровка не стартует: медленный TLS до api.omi.me

2026-10-15: ручная запись в Omi падает с «Omi transcription unavailable (connection or audio timed out)». Причина: `curl` до `https://api.omi.me/` показывает TLS 9,6 с и всего 11,4 с, а Omi ждал подключения 3 с (`CONNECT_TIMEOUT_MS` в `src/renderer/src/lib/transcriptionClient.ts`). Микрофон открывается только после подключения, поэтому в PipeWire потока не было.

Временная правка в форке: `CONNECT_TIMEOUT_MS` поднят до 20 с, `CAPTURE_START_TIMEOUT_MS` в `src/main/meeting/meetingMonitor.ts` — до 25 с, чтобы он был больше тайм-аута подключения. Надежное решение — VPN на уровне системы или локальная расшифровка.

## Данные с машины (T2)

Имена процессов из `/proc/<pid>/exe`:

| Программа | Путь | Имя для шаблона |
|---|---|---|
| eXpress | `/opt/eXpress/express` | `express` |
| Битрикс24 | `/opt/Bitrix24/Bitrix24` | `bitrix24` |
| Яндекс Браузер | `/opt/yandex/browser/yandex_browser` (`yandex-browser` — скрипт-обертка) | `yandex_browser` |
| Chrome | `/opt/google/chrome/chrome` | `chrome` |
| Omi в `pnpm dev` | `.../node_modules/electron/dist/electron` | `electron` |

Telegram на машине не установлен (ни deb, ни Flatpak, ни Snap). Flatpak не установлен вообще.

eXpress, 2026-10-15 21:10: открыт, звонка нет, потока `Stream/Input/Audio` нет. Утром поток был в состоянии `running`, значит, eXpress держит микрофон не всегда. Нужно понять, когда он его берет.

## Жизнь с Omi (T10)

Пока пусто.
