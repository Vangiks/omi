# Спецификация: модели через OpenRouter

Модуль `llm-openrouter` из `CAPABILITY-MAP.md`.

Статус: отложено. `local-backend` работает на прямых ключах. T1 и T2 были сделаны и откачены (коммиты `efb5123f5e`, `da8fa39a93`), их можно вернуть через `git revert` отката. Обновлено: 2026-10-16.

## Цель

Все, что OpenRouter умеет, бэкенд Omi делает через него. Прямые ключи провайдеров нужны только для того, чего OpenRouter не умеет. Модели не меняются: где была модель OpenAI, остается она же через OpenRouter; так же с Anthropic, Gemini и Perplexity.

Правило выбора для функций, которые OpenRouter поддерживает:

| `OPENROUTER_API_KEY` | Прямой ключ провайдера | Куда идет запрос |
|---|---|---|
| есть | любой | в OpenRouter, та же модель |
| нет | есть | напрямую к провайдеру, как сейчас |
| нет | нет | как сейчас: ошибка или функция выключена |

Для функций, которые OpenRouter не поддерживает, правило не применяется: они работают с прямым ключом, как сейчас, или выключены. Поддержку `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` и `PERPLEXITY_API_KEY` не убираем.

## Карта функций

### Через OpenRouter

| Функция | Где в коде | Модели | Этап |
|---|---|---|---|
| Сводки, задачи, память, чат-агент, уведомления, цели (около 50 функций) | шлюз, линии OpenAI | `openai/gpt-6-luna`, `openai/gpt-5-nano` | 1 |
| Чат десктопа | шлюз и `routers/desktop_chat.py`, Anthropic | `anthropic/claude-sonnet-4.6` и другие | 1 |
| Эмбеддинги для поиска по памяти | шлюз, `utils/llm/clients.py` | `openai/text-embedding-3-large` | 1 |
| Поиск в интернете в чате | шлюз, провайдер `perplexity` | `perplexity/sonar-pro` | 1 |
| Анализ экрана, фокус, задачи и память с экрана, профиль, цели | `routers/desktop_proxy.py`, прокси Gemini | `google/gemini-...` | 2 |
| Эмбеддинги Rewind, `gemini_embed_query` | прокси и шлюз | `google/gemini-embedding-001` | 2 |
| Линии Gemini в шлюзе (сейчас Vertex AI) | `VertexGeminiProvider` | `google/...` | 2 |
| Озвучка ответов | `utils/tts.py`, `routers/desktop_tts_updates.py` | Gemini TTS, OpenAI TTS | 2 |
| Вложения в чате | `utils/other/chat_file.py` | те же модели; файл хранится у нас и вкладывается в запрос | 2 |

### Только прямыми ключами: OpenRouter этого не умеет

| Функция | Ключ | Без ключа |
|---|---|---|
| Голосовой режим OpenAI Realtime (`routers/omni_relay.py`, `routers/desktop_realtime.py`) | `OPENAI_API_KEY` | выключен |
| Голосовой режим Gemini Live (клиент, `renderer/src/lib/voice/hub/`) | `GEMINI_API_KEY` | выключен |
| Распознавание речи: запись, созвоны, голосовые сообщения | `DEEPGRAM_API_KEY` | нет расшифровок. У OpenRouter распознавание только из готового файла, без потока |

До этапа 2 функции из второй половины первой таблицы тоже работают только с прямыми ключами Gemini и OpenAI.

Вложения в чате на этапе 1 нужно явно оставить на прямом ключе OpenAI. Файл загружается в хранилище OpenAI, а модель получает только его `file_id`. Вопрос к файлу идет через линии шлюза `omi:auto:file-chat-*` (функции `file_chat_documents` и `file_chat_vision`). Если шлюз отправит такой запрос в OpenRouter, тот не найдет файл. Поэтому эти линии остаются на прямом ключе, пока этап 2 не перенесет файлы к нам. Без `OPENAI_API_KEY` вложения в чате не работают.

### Не делаем

| Функция | Почему |
|---|---|
| Генерация картинок (`llm_gateway/routers/openai_compatible.py:368`) | OpenRouter умеет (`/api/v1/images`), но картинки рисуются только для иконок магазина приложений, а магазин мы не используем. Остается на прямом `OPENAI_API_KEY` |

## Что есть сейчас

- `utils/llm/model_config.py` назначает каждой функции модель и провайдера.
- Вызовы `get_llm()` без BYOK всегда идут через шлюз: `should_route_company_paid_features_through_gateway()` возвращает `True` (`utils/llm/gateway_client.py:231`). Основная работа — в провайдерах шлюза.
- Реестр шлюза (`llm_gateway/routers/dependencies.py:19-36`): `openai`, `openrouter`, `perplexity` (класс `OpenAICompatibleChatCompletionProvider`), `gemini` (`VertexGeminiProvider`), `anthropic` (`AnthropicMessagesProvider`).
- Anthropic в шлюзе вызывается еще и через сквозной роутер `llm_gateway/routers/anthropic_messages.py` (адрес зашит в `:41`). Оба пути шлют ключ в `x-api-key`.
- Проверка готовности шлюза требует прямые ключи (`llm_gateway/routers/health.py:29,34,39`).
- Исполнитель шлюза чистит запросы по признаку `provider_ref.provider == 'openai'` (`gateway/executor.py:780,814`). Поэтому подмену на OpenRouter делаем внутри класса провайдера, имя провайдера в маршруте не меняем.
- Прямые клиенты в обход шлюза: `get_or_create_openai_compatible_llm` в `utils/llm/providers.py:75`, эмбеддинги и клиент Anthropic по умолчанию в `utils/llm/clients.py:205,286`, `get_openai_chat` и `llm_mini` там же.
- `utils/llm/providers.py` уже знает провайдера `openrouter`. Функция `_api_model_name` добавляет префикс только моделям Gemini (`google/...`).

## Что проверено

- На OpenRouter есть `openai/gpt-6-luna`, `openai/gpt-5-nano`, `openai/text-embedding-3-large`, `google/gemini-embedding-001`, `perplexity/sonar-pro`.
- API в формате Anthropic: адрес `https://openrouter.ai/api`, ключ в `Authorization: Bearer`. Модели Anthropic названы через точку и без даты: `anthropic/claude-sonnet-4.6`.
- Озвучка: `/api/v1/audio/speech`, есть Gemini Flash TTS и OpenAI TTS.
- PDF и картинки принимаются прямо в сообщении (`file` с base64, `image_url`).
- API для голосового режима в реальном времени у OpenRouter не нашел.

## Этапы

### Этап 1: OpenAI, Anthropic, Perplexity

1. Новый модуль `utils/llm/openrouter.py`:
   - `provider_route(provider)` возвращает `openrouter`, `direct` или `none` по таблице выше;
   - `openrouter_model_id(provider, model)` переводит имя модели в формат OpenRouter.
2. Шлюз, OpenAI и Perplexity: `OpenAICompatibleChatCompletionProvider` при маршруте `openrouter` берет адрес и ключ OpenRouter и переводит имя модели. Касается чата и эмбеддингов (`create_embedding`). Исключение — линии `omi:auto:file-chat-*`: они остаются на прямом ключе OpenAI. Проверка готовности принимает ключ OpenRouter вместо прямых.
3. Шлюз, Anthropic: `AnthropicMessagesProvider` и `routers/anthropic_messages.py` при маршруте `openrouter` идут на `https://openrouter.ai/api/v1/messages` с `Authorization: Bearer` и переведенным именем модели. Проверка готовности принимает ключ OpenRouter.
4. Бэкенд в обход шлюза: те же правила для `providers.py` (маршрут в ключе кэша) и `clients.py` (эмбеддинги, `AsyncAnthropic(base_url='https://openrouter.ai/api', auth_token=<ключ>)`, `get_openai_chat`, `llm_mini`). Клиенты BYOK не трогаем.

### Этап 2: Gemini, озвучка, вложения

1. `routers/desktop_proxy.py`: при маршруте `openrouter` переводить `generateContent`, `streamGenerateContent` и `embedContent` из формата Gemini в OpenAI-совместимый формат OpenRouter и ответы обратно.
2. Линии Gemini в шлюзе: выяснить, какие функции на них, и направить их в OpenRouter.
3. Озвучка: `utils/tts.py` и `routers/desktop_tts_updates.py` через `/api/v1/audio/speech` с теми же моделями.
4. Вложения: `utils/other/chat_file.py` при маршруте `openrouter` хранит файл в нашем бакете `chat-files` (локально — на диске) и вкладывает содержимое в запрос вместо `file_id`.

Этап 2 разбиваем на задачи после проверки этапа 1 в `local-backend`.

## Стек

Python 3.11 (как в `backend/Dockerfile`), окружение через `uv` и `pylock.toml`. Используем то, что уже есть: `langchain_openai`, SDK `anthropic`, `httpx`, `pytest`. Новых зависимостей нет.

## Команды

Все команды из `backend`.

```bash
./scripts/sync-python-deps.sh                                   # .venv из .python-version и pylock.toml
.venv/bin/python -m pytest tests/unit/test_openrouter_routing.py -q
.venv/bin/python -m pytest tests/unit -q -k "provider or gateway or model_config"
bash scripts/run-unit-ci.sh                                     # полный набор юнит-тестов
```

## Структура

```
backend/utils/llm/
  openrouter.py                    новый: выбор маршрута и имена моделей
  providers.py                     openai через OpenRouter, общий перевод имен
  clients.py                       эмбеддинги и Anthropic по правилу
backend/llm_gateway/
  gateway/providers.py             OpenAI, Perplexity и Anthropic через OpenRouter
  routers/anthropic_messages.py    сквозной Anthropic через OpenRouter
  routers/health.py                ключ OpenRouter вместо прямых
backend/tests/unit/
  test_openrouter_routing.py       новый
backend/.env.template              OPENROUTER_API_KEY с комментарием о правиле
```

Этап 2 добавляет `routers/desktop_proxy.py`, `utils/tts.py`, `routers/desktop_tts_updates.py`, `utils/other/chat_file.py` и тесты к ним.

## Стиль кода

Как в `utils/llm/providers.py`: чистые функции без сетевых вызовов, типы на всех параметрах, комментарии на английском и объясняют «зачем».

```python
_OPENROUTER_VENDOR = {'openai': 'openai', 'anthropic': 'anthropic', 'gemini': 'google', 'perplexity': 'perplexity'}


def openrouter_model_id(provider: str, model: str) -> str:
    """Map a provider-native model id to its OpenRouter slug.

    OpenRouter names Anthropic versions with a dot and no date suffix:
    claude-haiku-4-5-20251001 -> anthropic/claude-haiku-4.5.
    """
    if '/' in model:
        return model
    if provider == 'anthropic':
        model = re.sub(r'-\d{8}$', '', model)
        model = re.sub(r'-(\d+)-(\d+)$', r'-\1.\2', model)
    return f'{_OPENROUTER_VENDOR[provider]}/{model}'
```

## Тестирование

- **Юнит-тесты без сети** в `tests/unit/test_openrouter_routing.py`:
  - таблица имен: все модели из `model_config.py`, `route_artifacts.yaml`, `generated_route_overrides.yaml` и псевдонимов `desktop_chat.py` переводятся без ошибок; отдельные случаи для дат и версий Anthropic;
  - `provider_route` для всех сочетаний переменных окружения;
  - фабрики клиентов: при маршруте `openrouter` у `ChatOpenAI`, `OpenAIEmbeddings`, `AsyncAnthropic` и провайдеров шлюза нужные адрес, ключ и модель; без ключа OpenRouter все как раньше.
- **Существующие тесты** провайдеров и шлюза проходят без изменений: без `OPENROUTER_API_KEY` прямые ключи работают по-старому.
- **Ручная проверка с реальными вызовами** стоит денег, поэтому запускаю ее сам: по одному запросу на каждую модель из списка через OpenRouter, на сумму меньше $0,10.

## Границы

- **Всегда:** без `OPENROUTER_API_KEY` поведение не меняется; писать код так, чтобы его можно было отправить в Omi отдельным PR; запускать юнит-тесты провайдеров и шлюза перед коммитом.
- **Сначала спросить:** изменения в `model_config.py` и выборе моделей; новые зависимости; реальные вызовы моделей за деньги; пуш в `origin` и PR в upstream.
- **Никогда:** коммитить ключи; подменять модель на другую ради цены или доступности; молча переключаться между OpenRouter и прямым ключом при ошибке.

## Критерии готовности

1. Задан `OPENROUTER_API_KEY`: сводка разговора, извлечение воспоминаний и задач, чат десктопа, эмбеддинги и поиск в интернете работают, запросы уходят на `openrouter.ai` с именами `openai/gpt-6-luna`, `openai/gpt-5-nano`, `anthropic/claude-sonnet-4.6`, `openai/text-embedding-3-large`, `perplexity/sonar-pro`, даже если заданы прямые ключи.
2. Заданы `OPENROUTER_API_KEY` и `OPENAI_API_KEY`: голосовой режим OpenAI Realtime работает с прямым ключом, все остальное — через OpenRouter.
3. Без `OPENROUTER_API_KEY` поведение не отличается от текущего: существующие тесты зеленые.
4. Новые юнит-тесты покрывают все модели из конфигурации и все сочетания ключей.
5. Этап 2: анализ экрана, озвучка и вложения в чате работают с одним ключом OpenRouter.

## Открытые вопросы

1. **Принимает ли API OpenRouter в формате Anthropic родные имена** (`claude-sonnet-4-6`). Если да, перевод имен для Anthropic не нужен. Проверить одним запросом.
2. **Кэширование промптов.** Бэкенд передает `cache_control` для Anthropic и параметры кэша для OpenAI. Проверить, что OpenRouter их пропускает, иначе вырастет цена.
3. **Ответы строго по схеме** (structured output) через OpenRouter для `gpt-6-luna`. Проверить на сводке разговора.
4. **Линии Vertex в шлюзе.** Какие функции на них сидят. Выяснить в начале этапа 2.
