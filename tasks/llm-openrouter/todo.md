# Задачи: модели через OpenRouter

План и обоснования: `tasks/llm-openrouter/plan.md`. Команды запускать из `backend` после `./scripts/sync-python-deps.sh`.

Обозначения проверок:
- `pytest:or` = `.venv/bin/python -m pytest tests/unit/test_openrouter_routing.py -q`
- `pytest:gw` = `.venv/bin/python -m pytest tests/unit -q -k llm_gateway`
- `pytest:llm` = `.venv/bin/python -m pytest tests/unit -q -k "provider or embeddings or anthropic or qos or byok"`

---

### T1. Правило выбора и имена моделей

**Что сделать:** модуль `utils/llm/openrouter.py` с `provider_route(provider)` (`openrouter`, `direct`, `none` по таблице из спеки: ключ OpenRouter важнее прямого) и `openrouter_model_id(provider, model)`.

**Готово, когда:**
- [x] `provider_route` дает верный ответ для провайдеров `openai`, `anthropic`, `perplexity` и всех сочетаний их прямых ключей с `OPENROUTER_API_KEY` (пустая строка считается отсутствием ключа)
- [x] все модели из `utils/llm/model_config.py`, `llm_gateway/config/route_artifacts.yaml`, `generated_route_overrides.yaml` и псевдонимов `routers/desktop_chat.py:234-243` переводятся без исключений; тест собирает их из конфигурации, а не из списка в тесте
- [x] отдельные случаи: `gpt-6-luna` → `openai/gpt-6-luna`, `claude-sonnet-4-6` → `anthropic/claude-sonnet-4.6`, `claude-haiku-4-5-20251001` → `anthropic/claude-haiku-4.5`, имя с `/` не меняется

**Проверка:** `pytest:or`

**Зависит от:** —

**Файлы:** `utils/llm/openrouter.py`, `tests/unit/test_openrouter_routing.py`

**Размер:** S

---

### T2. Шлюз: OpenAI и Perplexity через OpenRouter

**Что сделать:** `OpenAICompatibleChatCompletionProvider` для провайдеров `openai` и `perplexity` при маршруте `openrouter` берет адрес `https://openrouter.ai/api/v1`, ключ OpenRouter и переводит `request['model']`. То же в `create_embedding`. `routers/health.py` считает OpenAI и Perplexity готовыми при ключе OpenRouter.

**Готово, когда:**
- [x] с `OPENROUTER_API_KEY` (заданный `OPENAI_API_KEY` не мешает) запрос чата уходит на `openrouter.ai/api/v1/chat/completions` с `Authorization: Bearer <ключ OpenRouter>` и моделью `openai/gpt-6-luna`
- [x] эмбеддинги уходят на `openrouter.ai/api/v1/embeddings` с моделью `openai/text-embedding-3-large`
- [x] запрос Perplexity уходит туда же с моделью `perplexity/sonar-pro`
- [x] запросы линий `omi:auto:file-chat-*` (вложения в чате, `file_id` из хранилища OpenAI) идут на прямой ключ OpenAI даже при заданном ключе OpenRouter; без `OPENAI_API_KEY` — понятная ошибка, а не 404 от OpenRouter
- [x] без `OPENROUTER_API_KEY` запросы идут как раньше; BYOK-режим не меняется
- [x] проверка готовности проходит с одним ключом OpenRouter

**Заметки после выполнения:**
- Вложения узнаются по содержимому запроса, а не по имени линии: провайдер не знает линию. На прямом ключе остаются запросы с частью `{type: file, file: {file_id}}`. Это линия документов. Картинки в линии `file-chat-vision` идут base64 и уходят в OpenRouter.
- `tests/conftest.py` задает фейковый `OPENROUTER_API_KEY` для всех тестов, поэтому три негативных теста («ключей нет») теперь убирают и его. Из guardrail-теста убраны две устаревшие записи `health.py`. В T4 это коснется больше тестов.

**Проверка:** `pytest:gw` (новые случаи в стиле `test_llm_gateway_openai_provider.py:19`, через `httpx.MockTransport`)

**Зависит от:** T1

**Файлы:** `llm_gateway/gateway/providers.py`, `llm_gateway/routers/health.py`, `tests/unit/test_llm_gateway_openai_provider.py`, `tests/unit/test_llm_gateway_readiness.py`

**Размер:** M

---

### T3. Шлюз: Anthropic через OpenRouter

**Что сделать:** `AnthropicMessagesProvider` и `routers/anthropic_messages.py` при маршруте `openrouter` идут на `https://openrouter.ai/api/v1/messages` с `Authorization: Bearer` вместо `x-api-key` и переведенной моделью. `routers/health.py` считает Anthropic готовым при ключе OpenRouter.

**Готово, когда:**
- [ ] с `OPENROUTER_API_KEY` (заданный `ANTHROPIC_API_KEY` не мешает) оба пути шлют запрос на OpenRouter с Bearer-ключом и моделью `anthropic/...`; заголовки `anthropic-version` и `anthropic-beta` сохраняются
- [ ] без `OPENROUTER_API_KEY` запросы идут как раньше; BYOK-заголовок `x-omi-byok-anthropic-key` работает как раньше
- [ ] проверка готовности проходит с одним ключом OpenRouter

**Проверка:** `pytest:gw` (случаи в `test_llm_gateway_openai_provider.py` для Anthropic и в `test_llm_gateway_anthropic_passthrough.py`)

**Зависит от:** T1

**Файлы:** `llm_gateway/gateway/providers.py`, `llm_gateway/routers/anthropic_messages.py`, `llm_gateway/routers/health.py`, `tests/unit/test_llm_gateway_anthropic_passthrough.py`, `tests/unit/test_llm_gateway_openai_provider.py`

**Размер:** M

---

### Контрольная точка 1: шлюз

- [ ] `pytest:gw` и `pytest:or` зеленые
- [ ] существующие тесты шлюза не менялись, кроме добавленных случаев
- [ ] показать дифф, обсудить, прежде чем трогать бэкенд

---

### T4. Бэкенд в обход шлюза

**Что сделать:** то же правило для прямых клиентов: `get_or_create_openai_compatible_llm` в `utils/llm/providers.py` (провайдер `openai`; маршрут в ключе кэша), эмбеддинги по умолчанию, клиент Anthropic по умолчанию (`AsyncAnthropic(base_url='https://openrouter.ai/api', auth_token=...)`), `get_openai_chat` и `llm_mini` в `utils/llm/clients.py`.

**Готово, когда:**
- [ ] при маршруте `openrouter` фабрики создают клиентов с адресом и ключом OpenRouter и переведенной моделью; тест на кэш: смена ключей между вызовами дает разных клиентов
- [ ] без `OPENROUTER_API_KEY` ничего не меняется; клиенты BYOK не затронуты
- [ ] `utils/llm/shaped_notes_transport.py` копирует `api_key` и `base_url` из `ChatAnthropic`: проверить, что для OpenRouter копируется и Bearer-авторизация, или зафиксировать, что этот путь не используется

**Проверка:** `pytest:llm` (новые случаи в `test_llm_provider_plugin_structure.py` по образцу `:138` и в `test_embeddings_gateway.py`)

**Зависит от:** T1

**Файлы:** `utils/llm/providers.py`, `utils/llm/clients.py`, `tests/unit/test_llm_provider_plugin_structure.py`, `tests/unit/test_embeddings_gateway.py`

**Размер:** M

---

### T5. Документация и полный прогон

**Что сделать:** в `.env.template` описать `OPENROUTER_API_KEY` и правило выбора. Прогнать полный набор юнит-тестов.

**Готово, когда:**
- [ ] в `.env.template` рядом с ключами OpenAI и Anthropic объяснено правило: при заданном ключе OpenRouter поддерживаемые функции идут через него, прямые ключи нужны для голосового режима и (до этапа 2) для Gemini, озвучки и вложений в чате
- [ ] полный прогон без новых падений относительно `main`

**Проверка:** `bash scripts/run-unit-ci.sh`

**Зависит от:** T2, T3, T4

**Файлы:** `.env.template`

**Размер:** XS

---

### T6. Проверка на реальных моделях (за деньги, только с разрешения)

**Что сделать:** скрипт `scripts/openrouter_smoke.py`: по одному короткому запросу через провайдеры шлюза на каждую модель из конфигурации и один запрос сводки разговора со строгой схемой. Ответить на открытые вопросы 1–3 спеки и записать ответы в спеку.

**Готово, когда:**
- [ ] все модели отвечают через OpenRouter; суммарная стоимость меньше $0,10 по данным OpenRouter
- [ ] записано: принимает ли OpenRouter родные имена Anthropic, проходят ли параметры кэша, работает ли строгая схема для `gpt-6-luna`
- [ ] найденные несовместимости заведены задачами

**Проверка:** запуск скрипта с моим ключом, журнал в выводе

**Зависит от:** T5

**Файлы:** `scripts/openrouter_smoke.py`, `../SPEC-llm-openrouter.md`

**Размер:** S

---

### Контрольная точка 2: модуль готов

- [ ] критерии готовности 1–4 из спеки выполнены
- [ ] сводка разговора с одним ключом OpenRouter проходит в `local-backend` (контрольная точка A там)
- [ ] решить, разбивать ли этап 2 (Gemini и озвучка) на задачи сейчас
