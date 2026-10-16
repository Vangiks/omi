# Спека: убрать оплату и тарифы из форка (#3)

Файл живет только в ветке `feature/3-remove-billing` и удаляется последним коммитом перед мержем. Решения, которые нужны надолго, переносятся в комментарий к #3 и в `AGENTS.md`.

## Цель

В форке нет оплаты и тарифов. Любая функция работает без подписки у единственного пользователя локального стека (`deploy/local`), который работает на своих ключах.

Сейчас у локального пользователя подписки нет. Первое же чтение `get_user_subscription` (`backend/database/users.py`) записывает ему тариф `basic`, и он упирается во все проверки бесплатного тарифа: 402 `plan_gated` у `focus` и `task_extraction`, квоту чата, лимит минут расшифровки, блокировку разговоров (`is_locked`), платные функции вроде имен других спикеров, каналов сообщений и звонков.

Что остается:
- учет использования и расходов (`llm_usage`, `usage_tracker`, `managed_spend_ledger`, `llm_gateway_accounting`, `usage_units`, `user_usage`). Тариф в нем служит только меткой, ее заменяем константой;
- BYOK (`utils/byok.py`, `is_byok_active`, `request_has_llm_byok_key`);
- технические лимиты, не привязанные к тарифу: лимиты импорта (`database/import_quotas.py`), лимит голосовых сообщений (`utils/voice_duration_limiter.py`), частота запросов (`utils/rate_limit_config.py`). Значения ставим максимальными.

## Карта модулей

Работа делится на модули с постоянными id. Каждый модуль станет подзадачей #3.

| id | Что делает | Зависит от |
|---|---|---|
| `backend-unlock` | Одна точка: у любого пользователя полный доступ. Проверки тарифа пропускают всех, ничего нового не блокируется. Функции начинают работать | — |
| `backend-gates` | Удалить проверки тарифа и их вызовы: `managed_compute`, квоты чата, `trial_paywall`, лимит расшифровки, free-tier модули, проверки в спикерах, сообщениях, звонках, dream, proactivity, fair use | `backend-unlock` |
| `backend-locked` | Убрать 402 «A paid plan is required» для заблокированного контента и код восстановления. Поле `is_locked` в моделях остается для старых данных | `backend-unlock` |
| `backend-billing` | Удалить Stripe, PayPal, оплату, витрину тарифов, рефералы, `budget_choice`, overage, сверку и наблюдаемость оплаты, зависимость `stripe` | `backend-gates` |
| `backend-catalog` | Свернуть `plan_catalog` и `PlanType` до константы, убрать эндпоинты подписки и модели ответов, перегенерировать OpenAPI и клиенты TS | `backend-gates`, `backend-billing` |
| `desktop-billing` | Удалить из desktop экран «Тариф и использование», окно оплаты, квоту чата, всплывающее окно лимита, лист «Upgrade to Omi Pro», аналитику оплаты. Нейтральные тексты ошибок вместо «нужен тариф» | `backend-catalog` |
| `web-billing` | Удалить тарифы из `web/app` (вкладка тарифа в настройках, `PlansSheet`, воронка подписки, типы тарифов) и из `web/admin` (подписки, выручка, MRR, Stripe) | `backend-catalog` |
| `docs-rules` | Поменять правило о слиянии `upstream/main` в корневом `AGENTS.md`, убрать тарифы из `backend/AGENTS.md`, `web/admin/AGENTS.md` и публичной документации | все выше |

Порядок: `backend-unlock` → `backend-gates`, `backend-locked` → `backend-billing` → `backend-catalog` → `desktop-billing`, `web-billing` → `docs-rules`.

`backend-unlock` идет первым, потому что сразу дает рабочие функции. Это временный шаг, а не обертка совместимости: следующие модули удаляют то, что он обходит.

## Что именно меняется

### `backend-unlock`

- `get_user_subscription` и `get_user_valid_subscription` больше не записывают `basic` и возвращают действующий тариф с полным доступом.
- `has_transcription_credits` всегда `True`, чтобы новые разговоры не получали `is_locked=True`.
- Модули, которые читают `user['subscription']['plan']` из Firestore напрямую, мимо `get_user_valid_subscription`: `config/dream_agent.py`, `database/dream_store.py`, `config/proactivity_v2.py`, `database/llm_usage.py`, `database/llm_gateway_accounting.py`, `database/usage_units.py`, `utils/referrals.py`. Их нужно перевести на ту же точку, иначе они продолжат видеть `basic`.

### `backend-gates`

- `utils/managed_compute.py`: удалить `authorize_managed_compute` и вызовы в `routers/desktop_proxy.py` (`_enforce_managed_plan_gate`), `routers/desktop_task_gate.py` (`screen_task_gate`), `utils/mentor_admission.py`, `utils/conversations/process_conversation.py`, `utils/memory/daily_memory_sweep.py`, `utils/free_tier_memory_policy.py`.
- Если `screen_task_gate` после этого ничего не проверяет, удалить эндпоинт вместе с его вызовом в desktop.
- `utils/subscription.py`: удалить `enforce_chat_quota`, `enforce_desktop_chat_quota`, `is_trial_paywalled`, `is_desktop_trial_paywalled`, `resolve_transcription_allowance`, `should_defer_desktop_processing`, `should_skip_omi_paid_postprocessing`, `grants_cloud_screen_vectors` и остальные проверки. Помощники BYOK перенести в `utils/byok.py`.
- Удалить free-tier модули: `free_tier_processing_policy`, `free_tier_memory_policy`, `free_tier_basic_gates`, `free_tier_cohort`, `conversations/deterministic_minimum`.
- Проверки тарифа в `utils/speaker_permissions.py`, `utils/messaging/access.py`, `utils/phone_calls.py`, `config/dream_agent.py`, `config/proactivity_v2.py`, `routers/listen/runtime.py` (предупреждения freemium и Plus).
- Удалить fair use: `utils/fair_use.py`, `database/fair_use.py`, `models/fair_use.py`, `utils/llm/fair_use_classifier.py`, `routers/fair_use_admin.py`, вызовы в `routers/sync.py`, `routers/listen/runtime.py` (`check_soft_caps`), `utils/sync/pipeline.py`, `utils/listen_session_bootstrap.py`, индексы в `database/firestore_index_registry.py`, тесты `test_fair_use_*`. В `web/admin` удалить страницу `dashboard/fair-use`.

### `backend-locked`

- Удалить 402 «A paid plan is required» в `routers/action_items.py`, `conversations.py`, `conversation_mutations.py`, `folders.py`, `developer.py`, `mcp.py`, `users.py`, `speaker_labels.py`, `speaker_tag_prompts.py`, `utils/memory/memory_service.py`, `utils/agent_capabilities/errors.py`.
- Удалить `utils/locked_content_recovery.py`, `utils/locked_content_flags.py`, `database/locked_content.py`, хук в `utils/other/endpoints.py`, `scripts/unlock_soft_cap_locked.py`.
- Поле `is_locked` в моделях остается, читатели его больше не проверяют.

### `backend-billing`

- Удалить `routers/payment.py`, `routers/storefront.py`, `routers/referrals.py`, `routers/budget_choice.py` вместе с их модулями в `utils/`, `database/`, `models/`, `config/`, а также `utils/stripe.py`, ledgers, `subscription_state_machine`, `billing_reconciliation`, `overage`, наблюдаемость оплаты и метрику `omi_subscription_events_total`.
- Убрать регистрацию в `main.py` и `desktop_backend.py`, `validate_stripe_price_ids` при запуске, записи в `rate_limit_config.py`.
- Убрать рефералы из `routers/auth.py`, отмену подписки Stripe из `services/users/account_deletion.py`, сверку со Stripe из `routers/users.py`.
- Убрать `stripe` из `requirements.txt` и `openapi-requirements.txt`, перегенерировать `pylock*.toml`.
- Удалить скрипты оплаты: `billing_reconcile.py`, `plan_prices_dry_run.py`, `entitlement_catalog_validation.py`, `support/find_stripe_entitlement_mismatches.py`, `finops/pull_stripe.py`, `admin/reset_transcription_usage.py`.
- Удалить платные приложения маркетплейса: `utils/apps.py` (`paid_app`, `create_app_payment_link`, `find_app_subscription`, `get_is_user_paid_app`), поля `is_paid`/`payment_plan`, эндпоинт `/v1/app/payment-plans`, выплаты разработчикам (Stripe Connect, PayPal). Платных приложений у владельца форка нет.

### `backend-catalog`

- `config/plan_catalog.json`, `plan_catalog_generated.py`, `plan_catalog.py`, `scripts/generate_plan_catalog.py`: удалить. Тем, кто импортирует `PlanType` как метку (`llm_usage`, `usage_units`, `rate_card`, `sync/rate_limit`), оставить константу.
- Удалить эндпоинты `/v1/users/me/subscription`, `/usage-quota`, `/paywall`, `/trial` и модели `Subscription`, `PlanLimits`, `ChatUsageQuota`, `TrialMetadata` и подобные. Эндпоинты использования (`/v1/users/me/usage`, `llm-usage*`, `desktop-usage/daily`, `/v2/realtime/usage`) остаются.
- Заголовок `X-Omi-Plan-Identity` и `utils/plan_wire_capabilities.py` удалить.
- Перегенерировать `docs/api-reference/app-client-openapi.json` (`scripts/export_openapi.py`) и клиенты TS (`scripts/generate_ts_openapi_types.py`). Обновить `route_policy_manifest.yaml`, `route_policy_legacy_missing_routes.txt`, `scripts/check_response_model_coverage.py`, `scripts/select_backend_unit_tests.py`.

### `desktop-billing`

- Удалить `src/main/billing/checkoutWindow.ts`. Перед этим перенести обработчик `billing:openExternal` в `src/main/externalUrl.ts` и переименовать канал: им пользуются календарь, онбординг и приложения.
- Удалить `lib/billing.ts`, `billingPlans.ts`, `chatQuotaGate.ts`, `usageLimit.ts`, `components/settings/billing/*`, `tabs/PlanUsageTab.tsx`, вкладку `'plan-usage'` в `tabs.ts` и `Settings.tsx`, `UsageLimitTriggerHost`, `UsageLimitPopup`, `ClaudeAuthSheet` в `App.tsx`.
- `useChat.ts`: удалить `mainChatQuotaGate` и `quotaCheckSeq`. Строке бара: удалить `checkUsageLimit`, `limitNotice`, канал `bar:usageLimit`/`chat:barUsageLimit`. `usePushToTalk.ts`: удалить запрет по лимиту.
- `claudeSignIn.ts`: оставить вход в Claude OAuth, удалить лист и `OMI_PRICING_URL`.
- Тексты ошибок 402 и квоты в `ptt/transport.ts`, `voice/tokenMint.ts`, `transcriptionClient.ts` заменить нейтральными. Логику распознавания ответов сервера оставить.
- Удалить трекеры оплаты из `analytics.ts`, обновить `e2e/claude-signin.spec.mjs`.
- Вкладка «Тариф и использование» удаляется целиком. Отдельного экрана использования в desktop не будет, данные видны в web. Если экран понадобится, это отдельная задача.
- Удалить покупку платных приложений в `AppDetailSheet.tsx` (`is_paid`, `needsPurchase`, `paymentLink`).

### `web-billing`

- `web/app`: из `SettingsPage.tsx` удалить вкладку тарифа, обработчики оплаты, загрузку подписки и тарифов. Вкладку использования (`UsageChart`) оставить. Удалить `PlansSheet.tsx` (мертвый код), `TranscriptionUsageMeter.tsx`, `planFeatures.ts`, `analytics/subscriptionFunnel.ts`, типы тарифов в `types/user.ts`, функции подписки в `lib/api.ts`, `SegmentEditPlanRequiredError`, заголовок `X-Omi-Plan-Identity`.
- `web/admin`: удалить страницы подписок, выручки, MRR, экономики тарифов, выплат и партнерских выплат, их API-маршруты, `lib/stripe*.ts`, зависимость `stripe`, переменные `STRIPE_*`, дашборд «wall» в Grafana, если он строится на Stripe.
- `web/app`: убрать показ цены платных приложений (`AppDetail.tsx`, `apps/[id]`).

### `docs-rules`

- Корневой `AGENTS.md`: заменить правило о слиянии `upstream/main` на выборочный перенос вместе с агентом. Записать, что код оплаты из форка удален и изменения upstream в нем не переносятся.
- `backend/AGENTS.md`: удалить правило про `plan_catalog.json` (строка около 149) и упоминания подписки и Stripe. `web/admin/AGENTS.md`: удалить метрики выручки, если удаляются страницы.
- Публичная документация `docs/`: удалить упоминания тарифов в `onboarding/omi-macos.mdx`, `developer/mcp/tools.mdx`, `mcp/troubleshooting.mdx`, `backend/StoringConversations.mdx`, `backend/Backend_Setup.mdx`.
- `deploy/local/flags`: удалить флаги `BASIC_PLAN_GATE_*`, `FREE_TIER_*`, классификацию `STRIPE` в `flags/generate.py`.

## Не трогаем

- Облако Omi и свой сервер.
- `desktop/macos`: приложение сохранено для справки, его код не правим, хотя с новым бэкендом оно сломается на эндпоинтах подписки.
- Старые данные о подписках в Firestore: их просто никто не читает.
- Учет использования, BYOK, технические лимиты (кроме значений).

## Команды

Desktop (`desktop/windows`):

```bash
npx pnpm@10 typecheck
npx pnpm@10 lint
npx pnpm@10 test -- src/renderer/src/lib src/main   # нужный набор
```

Web (`web/app`, `web/admin`):

```bash
bunx tsc --noEmit && bunx vitest run --config vitest.config.mts   # web/app
```

Бэкенд (`backend`). Полный набор идет 20–30 минут, поэтому запускаем только затронутые файлы, каждый своим процессом:

```bash
python -m pytest tests/unit/test_desktop_proxy.py
python scripts/select_backend_unit_tests.py   # список тестов по измененным путям
python scripts/export_openapi.py && python scripts/generate_ts_openapi_types.py
```

Локальный стек:

```bash
docker compose -f deploy/local/docker-compose.yaml up -d --build
npx pnpm@10 dev:local    # в desktop/windows
docker compose -f deploy/local/docker-compose.yaml logs desktop-backend | grep -E 'plan_gated|trial_expired|quota_exceeded'
```

## Тесты

- Модули удаляются вместе со своими тестами. Это не ослабление проверок: тесты проверяют удаляемое поведение. Каждый удаленный тест перечисляется в описании коммита.
- В `backend-unlock` новый тест: пользователь без подписки проходит проверки, которые раньше давали 402 (`screen_task_gate`, прокси Gemini для `focus`, квота чата), и новый разговор не получает `is_locked`.
- Тесты, которые подменяют проверки (`test_desktop_proxy`, `test_stt_router`, `test_listen_runtime_regressions`, `useChat.test.tsx`, `usePushToTalk.test.tsx`, `ChatBridgeHost.test.tsx` и другие), правятся, а не удаляются.
- Каждый модуль заканчивается зеленым `typecheck`, `lint` и затронутыми тестами. Pre-push хук (`lefthook.yml`) не обходим.

## Границы

- Всегда: удалять код вместе с вызовами в том же коммите, не оставлять оберток совместимости. Сохранять BYOK и учет использования. Перегенерировать клиенты OpenAPI, а не править их руками.
- Спросить: удаление данных в Firestore, push в `origin`.
- Никогда: трогать `desktop/macos`, отключать проверки в хуках, удалять тест, который проверяет оставшееся поведение.

## Готово, когда

- [ ] В локальном стеке за сессию с анализом экрана, задачами с экрана, чатом и расшифровкой в логах `desktop-backend` и `backend` нет `plan_gated`, `trial_expired`, `quota_exceeded` и 402
- [ ] Новый разговор не получает `is_locked=True`
- [ ] В бэкенде нет `stripe` в зависимостях и нет `routers/payment.py`, `utils/subscription.py` (кроме переноса BYOK), `plan_catalog*`
- [ ] В desktop и web нет экрана тарифа, окна оплаты и всплывающего окна лимита
- [ ] Учет использования работает: `/v1/users/me/usage` отдает данные
- [ ] `typecheck`, `lint` и затронутые тесты desktop, web и бэкенда зеленые
- [ ] Корневой `AGENTS.md` описывает выборочный перенос из upstream

## Решения

- Платные приложения маркетплейса удаляются вместе с оплатой: у владельца форка их нет.
- Страницы оплаты, выручки и выплат в `web/admin` удаляются.
- Экрана использования в desktop после удаления вкладки тарифа нет, при необходимости это отдельная задача.
- Fair use удаляется: это защита облака от злоупотреблений, для одного локального пользователя она не нужна.
