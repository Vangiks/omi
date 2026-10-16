# Omi fork agent guide

Fork of BasedHardware/omi (`upstream`) at Vangiks/omi (`origin`). Scope: the Electron desktop
app in `desktop/windows`, developed and run on Linux, and `web/`. The mobile app, firmware,
omiGlass and device SDKs were removed. `CLAUDE.md` points here.

## Routes

| Working on | Read |
|---|---|
| Desktop app (Electron, Windows/Linux) | `desktop/windows/AGENTS.md` |
| Web app / admin | `web/app/AGENTS.md` / `web/admin/AGENTS.md` |
| Backend (the Omi server the clients call) | `backend/AGENTS.md` |
| macOS desktop (Swift, kept for reference) | `desktop/macos/AGENTS.md` |
| Public documentation | `docs/AGENTS.md` |
| Product behavior | `PRODUCT.md`, `product/invariants/` |
| Behavior shared with the macOS app | `contracts/parity/README.md` |
| Tasks, stages, which skill to start with | «Задачи: GitHub Issues» below, `.claude/skills/` |
| Capability map; specs and plans from before the issues process | `CAPABILITY-MAP.md`, `SPEC-*.md`, `tasks/` |

## Repository conventions

- Git hooks come from `lefthook.yml` and install with `npx pnpm@10 install` in `desktop/windows`.
  Pre-push runs desktop typecheck, lint and the meeting tests. Keep Git identity in the user's
  configuration; temporary test identities use `git -c`.
- `desktop/windows/package.json` pins pnpm 10 through `packageManager`, so corepack's `pnpm`
  picks the right version; without corepack use `npx pnpm@10`. pnpm 11 ignores
  `node-linker=hoisted`. Never run `npm install` there.
- The fork is the primary repository: issues, PRs and merges happen in `Vangiks/omi`. Ask before
  pushing to `origin`.
- Upstream release and PR tooling is gone from this fork (most of `.github/`, Codemagic,
  `make preflight`, `scripts/pr-preflight`). Do not rely on it or restore it.
- Migrate in-tree callers together rather than preserving retired APIs with compatibility wrappers.

## Задачи: GitHub Issues

Трекер задач — GitHub Issues `Vangiks/omi`. Скилл `planning-and-task-breakdown` заводит подзадачи как issues, а не пишет `tasks/todo.md`. Если `gh repo set-default --view` показывает не `Vangiks/omi`, поставьте его: иначе `gh` заведет issue или PR в `BasedHardware/omi`.

Скиллы проекта:

- `issue-add` — завести issues, например из замечаний после ревью.
- `using-issues` — взять issue в работу: выбрать следующий скилл, после шага оставить комментарий и сменить стадию.
- `skill-routing` — включить на всю сессию таблицу «событие → скилл agent-skills». Экспериментальный.

### Метки

У каждого issue две метки: тип и стадия.

- Тип: `type:bug`, `type:feature`, `type:refactor`. Тип не меняется.
- Стадия показывает, чего не хватает, чтобы начать работу. Стадия движется в одну сторону, любую можно пропустить:
  - `stage:discuss` — неясна цель. Для бага: неизвестна причина.
  - `stage:idea` — цель ясна, есть несколько вариантов решения. Для бага: причина известна, но исправить можно по-разному или неясно, стоит ли чинить вообще.
  - `stage:spec` — решение ясно, но работы больше чем на один заход. Нужны спека и план.
  - `stage:ready` — можно делать.

Стадию выбирают тремя вопросами:

1. Можно ли одним предложением сказать, какую проблему решаем и как поймем, что решили? Если нет, это `stage:discuss`.
2. Известно ли решение? Если нет или вариантов несколько, это `stage:idea`.
3. Хватит ли одного захода: один-два файла, без спеки? Если да, это `stage:ready`, иначе `stage:spec`.

### С какого скилла начинать

| | `stage:discuss` | `stage:idea` | `stage:spec` | `stage:ready` |
|---|---|---|---|---|
| `type:bug` | `debugging-and-error-recovery`: найти причину | `idea-refine` | `/spec`, потом `/plan` | `/test`: тест воспроизводит баг, потом исправление |
| `type:feature` | `interview-me` | `idea-refine` | `/spec`, потом `/plan` | есть подзадачи: `/build`, нет: `/test` |
| `type:refactor` | `interview-me` | `idea-refine` | `/spec`, потом `/plan` | есть подзадачи: `/build`, нет: `/code-simplify` |

Все скиллы и команды из таблицы — из плагина agent-skills.

### Правила

- Не переписывайте исходный текст issue. Уточнения пишите в комментарии. Исключение — галочки в разделе «Готово, когда»: пункт, который проверен, отмечайте `- [x]`.
- Сменили стадию — оставьте комментарий с результатом шага. Следующий агент берет из него все, что нужно для работы.
- `/plan` заводит подзадачи дочерними issues (`gh issue create --parent N`), у каждой свои метки. Зависимости между ними ставьте через `gh issue edit --add-blocked-by`.
- Родительский issue переходит в `stage:ready`, только когда все подзадачи в `stage:ready`. Иначе `/build` остановится на неясной подзадаче.
- Если задача в `stage:ready` оказалась больше одного захода, остановитесь и смените стадию на `stage:spec`.
- `SPEC.md` и `tasks/` для задачи живут только в ее рабочей ветке. Удалите их последним коммитом перед мержем. Решение, которое нужно сохранить надолго, запишите в ADR в `adr/` или в комментарий к issue.
- `SPEC-*.md` и `tasks/` в main остались от прежнего порядка работы, новые туда не добавляйте. `CAPABILITY-MAP.md` остается в main.
- Перед мержем проверьте код через `/agent-skills:review`. В Claude Code `/review` занят встроенной командой, поэтому команду плагина вызывайте с префиксом.
- Issue закрывает PR со строкой `Closes #N` в описании. Вручную issues не закрывайте. Исключение — задача, которую решили не делать: ее закрывает человек как not planned и пишет причину в комментарии.

Keep this file a router. Add component facts to the owning guide.
