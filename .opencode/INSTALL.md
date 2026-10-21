# OpenCode: подключение EWB 5.12 MCP

В репозитории намеренно нет готового `opencode.json`: этот файл импортируют
некоторые другие клиенты, и корневой MCP-сервер мог бы зарегистрироваться
дважды. Добавьте конфигурацию в проект или в глобальные настройки OpenCode.

## Вариант 1: проект

Создайте `opencode.json` в корне проекта, где лежат схемы:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ewb512": {
      "type": "local",
      "command": ["python3", "/absolute/path/to/ewb_mcp/scripts/server.py"],
      "enabled": true,
      "environment": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

Замените `/absolute/path/to/ewb_mcp/scripts/server.py` на реальный путь. На Windows
используйте `python` и путь вида `C:\\path\\to\\ewb_mcp\\scripts\\server.py` (в JSON
обратные слэши удваиваются).

## Вариант 2: глобально

Добавьте тот же блок `mcp` в `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ewb512": {
      "type": "local",
      "command": ["python3", "/absolute/path/to/ewb_mcp/scripts/server.py"],
      "enabled": true,
      "environment": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

Если файл уже существует, объедините объекты, не заменяйте остальные
настройки.

## Важно

- В OpenCode ключ называется `environment`, а не `env`.
- `command` — массив: первый элемент — исполняемый файл, остальные —
  аргументы.
- `cwd` не обязателен. Если он нужен, укажите абсолютный путь к каталогу
  `ewb_mcp`.
- Вместо `EWB_MCP_ALLOW_HOME` можно задать более строгий
  `EWB_MCP_ALLOWED_DIRS`:

```json
"environment": {
  "EWB_MCP_ALLOWED_DIRS": "/path/to/schematics:/tmp"
}
```

На Windows разделитель — `;`.

## После установки

1. Перезапустите OpenCode.
2. Убедитесь, что инструменты `ewb_list_parts`, `ewb_read_schematic` и
   `ewb_validate` доступны.
3. Попросите агента прочитать
   `/absolute/path/to/ewb_mcp/skills/ewb-schematics/SKILL.md`. Этот файл
   содержит обязательный порядок работы со схемами, правила координат,
   выводов и маршрутов.

## Проверка сервера вручную

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}' \
  | python3 /absolute/path/to/ewb_mcp/scripts/server.py
```

В ответе должно быть `"name": "ewb512-schematic"`.

Подробная установка для остальных клиентов — в
[`docs/INSTALL.md`](../docs/INSTALL.md).
