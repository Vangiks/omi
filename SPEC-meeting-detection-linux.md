# Спецификация: определение созвона на Linux

Модуль `meeting-detection-linux` из `CAPABILITY-MAP.md`. Этап 1 — модуль `linux-run`.

Статус: черновик, на утверждении. Обновлено: 2026-10-15.

## Цель

Когда я начинаю созвон в Telegram, eXpress, Zoom или в браузере, Omi на Linux сам это замечает и предлагает записать: «Записать?». После созвона запись останавливается, Omi делает расшифровку и сводку, как на Windows.

Сейчас на Linux это не работает. Логика определения общая для всех ОС: автомат состояний `detector.ts`, шаблоны `patterns.ts`, всплывающее окно, настройка в «General». Но два источника сигналов и запуск монитора есть только для Windows:

- `processSnapshot.ts`: список процессов через Toolhelp32; на Linux возвращает `[]`;
- `micConsentStore.ts`: кто держит микрофон, из реестра Windows; на Linux возвращает `[]` и `null`;
- `meetingMonitor.ts`: `startMeetingMonitor` выходит сразу, если `process.platform !== 'win32'`;
- `nativeForeground.ts`: `subscribeForegroundChange` на Linux ничего не делает. Активное окно и заголовок через `xprop` уже читаются.

Задача — дописать эти источники для Linux и добавить шаблоны программ, которыми пользуются в России. Логику принятия решений не трогаем.

### Пользовательские сценарии

1. Звоню в Telegram Desktop. Через 3–5 секунд после того, как Telegram взял микрофон, появляется окно «Записать?». Нажимаю «Да» — идет запись с микрофона и системного звука.
2. Звонок закончился. Через 2 минуты (стандартный `endGraceMs`) Omi сам останавливает запись.
3. Открываю Google Meet или Яндекс Телемост в Chrome и вхожу во встречу — то же самое.
4. Telegram просто открыт, без звонка. Ничего не происходит.
5. Omi сам пишет микрофон (кнопка «записать» вручную). Это не считается созвоном.
6. В настройках ставлю режим `off`. Определение не работает и не тратит ресурсы.

## Этап 1: `linux-run`

Форк собирается и запускается на моей машине без изменений в коде.

- Поставить зависимости: `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-rus` (`x11-utils` уже стоит).
- `.env` из `.env.example`, вход через свой аккаунт Omi.
- Пройти `typecheck`, `lint` и `test`, записать, что падает на Linux до наших изменений. Это база для сравнения.
- Пожить с Omi пару дней: что работает, что раздражает. Записать в `docs/naparnik/linux-run-notes.md`.

## Этап 2: определение созвона

### Источник 1: процессы (Tier 1)

Новый файл `src/main/meeting/linuxProcessSnapshot.ts`:
- читает `/proc/<pid>/exe` через `readlink` для всех числовых `pid` и берет имя файла в нижнем регистре;
- если `exe` недоступен (чужой процесс, нет прав), берет `/proc/<pid>/comm`;
- никогда не бросает исключений, при ошибке возвращает `[]`.

`processSnapshot.listProcessNames()` на Linux вызывает эту функцию.

### Источник 2: микрофон (Tier 2)

Новый файл `src/main/meeting/linuxMicCapture.ts`:
- запускает `pw-dump` (у меня отрабатывает за 0,23 с) и разбирает JSON;
- берет узлы с `media.class === 'Stream/Input/Audio'` в состоянии `running`;
- id записи — имя файла из `application.process.binary` в нижнем регистре. Пример с моей машины: eXpress дает `express`;
- исключает сам Omi: `application.process.binary` совпадает с именем `process.execPath` или `application.process.id` входит в дерево процессов Omi;
- разбор JSON — отдельная чистая функция `parsePwDumpMicEntries(json, selfExe)`. Ее покрываем тестами на сохраненных выводах `pw-dump`.

`micConsentStore.readMicCaptureEntries()` на Linux вызывает эту функцию. На Linux `watchMicConsentStore()` возвращает наблюдатель, который раз в 2 с опрашивает `pw-dump` и вызывает `onChange` только при изменении набора id.

### Смена активного окна

Для Linux `subscribeForegroundChange` раз в 2 с опрашивает `getLinuxForegroundInfo()` и вызывает колбэк, когда меняется окно или заголовок. Опрос нужен, чтобы ловить открытие вкладки Meet или Телемоста.

### Запуск монитора

`startMeetingMonitor` запускается на `win32` и `linux`. На других платформах поведение прежнее.

### Шаблоны программ

В `patterns.json` добавляем имена для Linux к существующим записям и новые программы. Имена ниже нужно проверить на моей машине (см. «Открытые вопросы»).

| id | Программа | Процессы на Linux |
|---|---|---|
| `zoom` | Zoom | `zoom` |
| `teams` | Microsoft Teams | `teams-for-linux` |
| `slack` | Slack | `slack` |
| `discord` | Discord | `discord` |
| `telegram` | Telegram | `telegram-desktop`, `telegram` |
| `express` | eXpress | `express` |
| `bitrix24` | Битрикс24 | `bitrix24` |

Браузеры для проверки заголовков: `chrome`, `chromium`, `firefox`, `opera`, `yandex_browser`, `msedge`, `brave`, `vivaldi`.

Новые шаблоны заголовков:

| id | Сервис | Шаблон |
|---|---|---|
| `telemost-web` | Яндекс Телемост | `Телемост` |
| `tolk-web` | Контур.Толк | `Толк` |
| `jazz-web` | SaluteJazz | `SaluteJazz` |
| `vk-calls-web` | VK Звонки | `VK Звонки` |

## Стек

Без новых зависимостей: Electron и TypeScript из проекта, `node:fs` и `node:child_process`, системные `pw-dump` и `xprop`. Node 22.19–22.x (у меня 22.23), pnpm 10 через `npx pnpm@10` (системный pnpm 11 ломает `node-linker=hoisted`).

## Команды

Все команды запускать из `desktop/windows`.

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus
cp .env.example .env
npx pnpm@10 install --frozen-lockfile
npx pnpm@10 dev                                  # запуск на X11
npx pnpm@10 test                                 # все юнит-тесты (vitest)
npx pnpm@10 exec vitest run src/main/meeting     # только модуль созвонов
npx pnpm@10 typecheck
npx pnpm@10 lint
```

## Структура

```
desktop/windows/src/main/meeting/
  linuxProcessSnapshot.ts         новый: процессы из /proc
  linuxProcessSnapshot.test.ts    новый
  linuxMicCapture.ts              новый: микрофон из pw-dump
  linuxMicCapture.test.ts         новый
  fixtures/pw-dump-*.json         новые: сохраненные выводы pw-dump
  processSnapshot.ts              ветка для linux
  micConsentStore.ts              ветка для linux
  meetingMonitor.ts               запуск на linux
  patterns.json                   имена для Linux и российские программы
  patterns.test.ts                тесты на новые шаблоны
desktop/windows/src/main/usage/
  nativeForeground.ts             subscribeForegroundChange для linux (опрос)
desktop/windows/changelog/unreleased/
  2026-10-linux-meeting-detection.json
docs/naparnik/
  linux-run-notes.md              заметки по этапу 1
```

## Стиль кода

Как в соседних файлах: разбор данных — чистая функция без Electron и ввода-вывода; системные вызовы — в тонкой обертке, которая никогда не бросает исключений и при ошибке возвращает пустой результат с `console.warn('[meeting] ...')`. Комментарии на английском, в стиле проекта: зачем, а не что.

```ts
// Tier 2 on Linux — which apps hold a running PipeWire capture stream.
// Pure: the caller runs `pw-dump` and passes stdout. Omi's own streams are
// excluded so self-capture never looks like a meeting.
export function parsePwDumpMicEntries(json: string, selfExe: string | null): MicCaptureEntry[] {
  let nodes: unknown
  try {
    nodes = JSON.parse(json)
  } catch {
    return []
  }
  if (!Array.isArray(nodes)) return []
  const ids = new Set<string>()
  for (const n of nodes) {
    const info = (n as { info?: { state?: string; props?: Record<string, unknown> } }).info
    const props = info?.props
    if (props?.['media.class'] !== 'Stream/Input/Audio' || info?.state !== 'running') continue
    const id = exeBasename(String(props['application.process.binary'] ?? ''))
    if (id && id !== selfExe) ids.add(id)
  }
  return [...ids].map((id) => ({ id, path: null, packaged: false }))
}
```

## Тестирование

- **Юнит-тесты (vitest)** рядом с кодом, в стиле `detector.test.ts`:
  - `parsePwDumpMicEntries`: идет звонок, микрофон свободен, только вывод звука, Omi пишет сам, битый JSON;
  - разбор `/proc`: обычный процесс, процесс без прав на `exe`, исчезнувший процесс;
  - `matchTier1` и `pickAgreedMatch` для Linux-имен: `telegram-desktop`, `express`, `chrome` с заголовком Телемоста;
  - валидность нового `patterns.json` (уже есть тест на встроенные шаблоны).
- **Фикстуры `pw-dump`** снимаю на своей машине во время реальных звонков в Telegram, eXpress и Meet.
- **Ручная проверка** по сценариям 1–6 из раздела «Цель», с логами `[meeting]` в консоли `pnpm dev`.
- Все существующие тесты остаются зелеными. Число тестов, которые падают на Linux до изменений, фиксируем на этапе 1.

## Границы

- **Всегда:** запускать `vitest` для `src/main/meeting`, `typecheck` и `lint` перед коммитом; писать код без привязки к нашему бэкенду, чтобы его можно было отправить в Omi отдельным PR; добавлять фрагмент в `changelog/unreleased/`.
- **Сначала спросить:** новые npm-зависимости; изменения в `detector.ts` и логике решений; изменения вне `src/main/meeting` и `src/main/usage`; пуш в `origin`; PR в `BasedHardware/omi`.
- **Никогда:** коммитить `.env` и ключи; запускать `npm install` (только pnpm 10); удалять или отключать падающие тесты без согласования; ломать поведение на Windows.

## Критерии готовности

1. Сценарии 1–6 проходят вручную на Ubuntu 24.04 (X11, PipeWire) для Telegram, eXpress и Google Meet в Chrome.
2. Окно «Записать?» появляется не позже чем через 5 с после того, как программа взяла микрофон.
3. Без звонка за час работы нет ни одного ложного окна (при открытых Telegram, eXpress и браузере).
4. Опрос в простое расходует не больше 2% одного ядра (`pidstat` по процессу Omi).
5. Новые юнит-тесты проходят, существующие не ломаются, `typecheck` и `lint` чистые.
6. На Windows поведение не меняется: ветки `win32` не тронуты.

## Открытые вопросы

1. **eXpress держит микрофон постоянно?** Сейчас (2026-10-15) у eXpress в `pw-dump` открыт поток `Stream/Input/Audio` в состоянии `running`. Если созвона нет, Omi будет считать созвоном все время, пока eXpress открыт. Варианты: смотреть, идет ли через поток реальный звук; требовать заголовок окна звонка; выключать eXpress по умолчанию через `perApp`. Проверить на этапе 1.
2. **Точные имена процессов** Telegram (deb, Flatpak, официальный архив), Битрикс24, Zoom и Яндекс Браузера на Linux. Проверить на машине и поправить таблицу.
3. **Заголовки вкладок** Телемоста, Контур.Толка, SaluteJazz и VK Звонков во время встречи. Снять реальные заголовки.
4. **Опрос или события.** Для начала опрос раз в 2 с. Если по критерию 4 выйдет дороже, перейти на `pw-dump --monitor` и `xprop -spy`.
5. **Flatpak и Snap.** В песочнице `application.process.binary` может отличаться от имени процесса. Решить, поддерживаем ли сразу.
6. **Отправлять ли модуль в Omi PR-ом** после проверки у себя.
