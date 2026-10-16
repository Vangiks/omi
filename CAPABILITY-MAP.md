# Карта модулей: напарник на ПК на основе Omi

Форк Omi (MIT) — основа своего продукта: напарник на ПК, который сам замечает, что делает человек, предлагает помощь и делает за него. Первые пользователи — я и российские компании, начиная с МКСКОМ. Первый профиль — продажник.

Обновлено: 2026-10-16.

| Модуль | Что делает | Зависит от |
|---|---|---|
| `linux-run` | Форк собирается, проходит тесты и запускается на Ubuntu 24.04 (X11) | — |
| `meeting-detection-linux` | Определение созвона на Linux: процессы из `/proc`, микрофон из PipeWire, шаблоны российских программ | `linux-run` |
| `commitments` | Договоренности из созвонов и напоминания о них. Сначала проверить, что уже есть в Omi | `meeting-detection-linux` |
| `llm-openrouter` | Отложено. Все, что умеет OpenRouter, бэкенд делает через него, с теми же моделями. Вернуться, когда дойдем до сокращения числа провайдеров | — |
| `local-backend` | Весь бэкенд Omi в Docker на моей машине, клиент ходит только в него, в контур Omi ничего не уходит | `linux-run` |
| `ru-backend` | Свой бэкенд на сервере: вход, расшифровка речи и модель, доступные в России | `local-backend` |
| `ru-integrations` | Битрикс24, amoCRM, Telegram, eXpress, 1С как инструменты агента | `ru-backend` |
| `sales-profile` | Профиль продажника: триггеры, сценарии, метрика пользы | `commitments`, `ru-integrations` |
| `linux-automation` | Кнопка «Выполнить» на Linux через AT-SPI и `xdotool` | `linux-run` |

Порядок: `linux-run` → `meeting-detection-linux` → `commitments` → `ru-backend` → `ru-integrations` → `sales-profile`. `local-backend` — параллельно с `meeting-detection-linux`, до `ru-backend`. `linux-automation` — параллельно, когда понадобится.

Работа по модулям ведется в GitHub Issues `Vangiks/omi`. `meeting-detection-linux` и `linux-run` как его первый этап — issue #8. `local-backend` сделан, стек и его ограничения описаны в `deploy/local/README.md`.

## Работа с оригиналом

- `origin` — `Vangiks/omi`, `upstream` — `BasedHardware/omi`.
- Пока бэкенд не разошелся с оригиналом, обновления забираем слиянием из `upstream/main`. После `ru-backend` — выборочно через cherry-pick.
- Изменения, полезные всем (например, `meeting-detection-linux`), держим так, чтобы их можно было отправить в Omi отдельным PR.
- Код закрывать будем в отдельном приватном репозитории: форк публичного проекта на GitHub приватным не сделать.
