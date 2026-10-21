# Установка EWB 5.12 MCP

Один и тот же сервер `scripts/server.py` устанавливается во все поддерживаемые
AI-среды. Различаются только формат манифеста и команда установки. Никакие
пакеты Python и сама Electronics Workbench не требуются.

В примерах ниже:

```bash
export EWB_HOME="$HOME/Git/ewb_mcp"
```

Замените путь на свой. Если репозиторий уже опубликован, вместо локального пути
можно использовать `OWNER/REPO` или URL репозитория; в этом документе такие
места помечены как `OWNER/REPO`.

Команды CLI в разных сборках клиентов могут отличаться. Если команда не
найдена, посмотрите `--help` у соответствующего клиента, установите плагин
через его интерфейс или подключите `scripts/server.py` вручную по разделу
[Claude Desktop, Windsurf, Cline, Continue, Zed](#claude-desktop-windsurf-cline-continue-zed).
Ручное подключение через stdio работает независимо от плагинной упаковки.

## Содержание

- [Общие требования](#общие-требования)
- [Быстрая проверка](#быстрая-проверка)
- [Claude Code](#claude-code)
- [Codex](#codex)
- [Cursor](#cursor)
- [Gemini CLI](#gemini-cli)
- [Qwen Code](#qwen-code)
- [OpenCode](#opencode)
- [Kimi Code](#kimi-code)
- [Muse](#muse)
- [Antigravity](#antigravity)
- [Devin CLI](#devin-cli)
- [Hermes Agent](#hermes-agent)
- [GitHub Copilot CLI](#github-copilot-cli)
- [VS Code](#vs-code)
- [Factory Droid](#factory-droid)
- [Qoder](#qoder)
- [Claude Desktop, Windsurf, Cline, Continue, Zed](#claude-desktop-windsurf-cline-continue-zed)
- [Обновление и удаление](#обновление-и-удаление)
- [Что проверить после установки](#что-проверить-после-установки)

## Общие требования

- Python 3.8 или новее, команда `python3` доступна в `PATH`.
- Внешние Python-пакеты не нужны.
- EWB устанавливать и запускать не требуется.
- Схемы должны лежать в разрешённых каталогах. По умолчанию это текущий
  каталог, каталог `ewb_mcp`, `/tmp` и `/private/tmp`. Плагинные конфигурации
  дополнительно включают домашний каталог через `EWB_MCP_ALLOW_HOME=1`.
- Если нужен только один каталог со схемами, задайте
  `EWB_MCP_ALLOWED_DIRS=/path/to/schematics` и не включайте домашний каталог.

Проверить сервер вручную можно так:

```bash
cd "$EWB_HOME"
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}' \
  | python3 scripts/server.py
```

В ответе должно быть `"serverInfo"` с именем `ewb512-schematic`.

## Быстрая проверка

```bash
cd "$EWB_HOME"
python3 -m unittest discover -s tests -v
```

Тесты не требуют EWB и не изменяют файлы за пределами временного каталога.

## Claude Code

В пакете есть `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
и `.mcp.json`.

Установка из локального каталога:

```bash
cd "$EWB_HOME"
claude plugin marketplace add "$PWD"
claude plugin install ewb512-schematics@ewb512-plugins
```

Те же команды внутри сессии Claude Code:

```text
/plugin marketplace add /path/to/ewb_mcp
/plugin install ewb512-schematics@ewb512-plugins
```

После публикации репозитория:

```text
/plugin marketplace add OWNER/REPO
/plugin install ewb512-schematics@ewb512-plugins
```

Перезапустите сессию, чтобы Claude Code подхватил MCP-сервер и skill. Проверка:

```bash
claude plugin details ewb512-schematics
```

Claude Code разворачивает `${CLAUDE_PLUGIN_ROOT}` в `.mcp.json`, поэтому сервер
запускается из каталога плагина и видит свои модули.

## Codex

В пакете есть три взаимодополняющих файла:

- `.agents/plugins/marketplace.json` — маркетплейс Agent Plugins;
- `.codex-plugin/plugin.json` — манифест Codex;
- `mcp.json` — MCP-конфигурация по схеме Agent Plugins 1.0.0.

Codex CLI:

```bash
cd "$EWB_HOME"
codex plugin marketplace add "$PWD"
codex plugin add ewb512-schematics@ewb512-plugins
codex plugin list
```

Если в вашей сборке нет `plugin add`, используйте
`codex plugin install ewb512-schematics@ewb512-plugins`.

В Codex App откройте боковую панель Plugins, найдите `EWB 5.12 Schematics` и
нажмите Install. Если в вашей сборке CLI команды называются иначе, посмотрите
`codex plugin --help` и `codex plugin marketplace --help`: синтаксис менялся
между версиями.

После публикации:

```bash
codex plugin marketplace add OWNER/REPO
codex plugin add ewb512-schematics@ewb512-plugins
```

## Cursor

В пакете есть `.cursor-plugin/plugin.json`. Cursor не раскрывает
`${PLUGIN_ROOT}`, поэтому манифест использует поддерживаемый Cursor
`${CURSOR_PLUGIN_ROOT}`.

Установка через интерфейс:

1. Откройте **Customize** в боковой панели.
2. Найдите локальный плагин или нажмите добавление плагина.
3. Укажите каталог `"$EWB_HOME"`.
4. Выберите область установки — проект или пользователь.

В чате Cursor также работает команда:

```text
/add-plugin /path/to/ewb_mcp
```

Для локальной разработки можно скопировать каталог в
`~/.cursor/plugins/local/ewb512-schematics` и выполнить
**Developer: Reload Window**.

Если MCP-сервер не появился, добавьте его вручную в `.cursor/mcp.json`
проекта:

```json
{
  "mcpServers": {
    "ewb512": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

## Gemini CLI

В пакете есть `gemini-extension.json` и `GEMINI.md`. Путь к серверу вычисляется
через `${extensionPath}`.

```bash
cd "$EWB_HOME"
gemini extensions install "$PWD"
```

Для разработки удобнее ссылка, а не копирование:

```bash
gemini extensions link "$PWD"
```

Список подкоманд зависит от версии Gemini CLI; актуальный синтаксис показывает
`gemini extensions --help`.

## Qwen Code

Qwen Code использует формат расширений Gemini CLI, поэтому отдельный манифест
не нужен:

```bash
cd "$EWB_HOME"
qwen extensions install "$PWD"
```

Обновление:

```bash
qwen extensions update ewb512-schematics
```

Если ваша версия Qwen Code ещё не поддерживает `gemini-extension.json`,
подключите `scripts/server.py` как обычный stdio MCP-сервер по разделу
[Claude Desktop, Windsurf, Cline, Continue, Zed](#claude-desktop-windsurf-cline-continue-zed).

## OpenCode

Готового `opencode.json` в репозитории намеренно нет: его импортируют некоторые
другие клиенты, и это могло бы создать дубликат MCP-сервера. Вместо этого
инструкция лежит в `.opencode/INSTALL.md`.

Если вы открыли каталог `ewb_mcp` как проект OpenCode, создайте в корне
`opencode.json`:

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

Важно: в OpenCode ключ называется `environment`, а не `env`.

Для глобальной установки положите этот блок в
`~/.config/opencode/opencode.json`. После изменения конфигурации перезапустите
OpenCode. Затем попросите агента прочитать
`skills/ewb-schematics/SKILL.md` — этот файл содержит рабочие правила для
`.ewb`.

## Kimi Code

В пакете есть `.kimi-plugin/plugin.json` с `skills`, `mcpServers` и
`sessionStart.skill`.

```text
/plugins install /path/to/ewb_mcp
```

Или через Marketplace в интерфейсе Kimi Code. После публикации можно указать
URL репозитория.

Манифест запускает `scripts/server.py` из корня плагина и передаёт
`EWB_MCP_ALLOW_HOME=1`. Skill `ewb-schematics` загружается в начале сессии.

## Muse

В пакете есть `.muse-plugin/plugin.json` и `.muse-plugin/marketplace.json`.
Muse не передаёт `env` для MCP-серверов в манифесте, поэтому используется
маленький launcher `scripts/ewb_mcp_launcher.py`, который включает доступ к
домашнему каталогу и запускает `scripts/server.py`.

```bash
cd "$EWB_HOME"
muse plugins install "$PWD"
muse plugins approve ewb512-schematics
```

Обновление:

```bash
muse plugins update ewb512-schematics
```

Проверить пакет до установки:

```bash
muse plugins validate "$EWB_HOME" --json
```

## Antigravity

В пакете есть `.antigravity-plugin/plugin.json` и корневой `mcp_config.json`.

```bash
agy plugin install /path/to/ewb_mcp
```

После публикации:

```bash
agy plugin install https://github.com/OWNER/REPO
```

Antigravity читает MCP-серверы из `mcp_config.json` в корне плагина. Если
ваша версия устанавливает плагин в другой каталог или не подхватывает
`mcp_config.json`, добавьте сервер вручную.

Глобально: `~/.gemini/config/mcp_config.json`.

В проекте: `.agents/mcp_config.json`.

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

В Antigravity для stdio используется `command` и `args`; поле `serverUrl`
предназначено для удалённых серверов.

## Devin CLI

В пакете есть `.devin-plugin/plugin.json`. MCP-сервер объявлен прямо в
манифесте, а skills берутся из `skills/`.

```bash
cd "$EWB_HOME"
devin plugins install --local "$PWD"
devin plugins list
```

После публикации:

```bash
devin plugins install OWNER/REPO
```

Skill вызывается с пространством имён плагина, например
`/ewb512-schematics:ewb-schematics`. Если Devin попросит подтвердить доступ к
каталогу, разрешите только каталог со схемами и, при необходимости, домашний
каталог.

## Hermes Agent

Hermes поддерживает переносимые пакеты Agent Plugins: корневой `plugin.json`,
`skills/` и `mcp.json`. Наш корневой `plugin.json` и `mcp.json` уже соответствуют
этой схеме, поэтому отдельный `.hermes-plugin` не нужен.

```bash
hermes plugins install /path/to/ewb_mcp --enable
```

После публикации:

```bash
hermes plugins install OWNER/REPO --enable
```

Перезапустите сессию Hermes. Инструменты появятся с префиксом
`mcp__ewb512__`, а skill — в пространстве имён плагина.

## GitHub Copilot CLI

Copilot CLI понимает формат маркетплейса Claude Code:

```bash
cd "$EWB_HOME"
copilot plugin marketplace add "$PWD"
copilot plugin install ewb512-schematics@ewb512-plugins
```

После публикации:

```bash
copilot plugin marketplace add OWNER/REPO
copilot plugin install ewb512-schematics@ewb512-plugins
```

## VS Code

В репозитории уже есть `.vscode/mcp.json`. Откройте каталог `ewb_mcp` в VS Code,
затем откройте панель MCP Servers и запустите `ewb512`. Конфигурация использует
`${workspaceFolder}/scripts/server.py`.

Если VS Code открывает другой проект, скопируйте блок в `.vscode/mcp.json`
этого проекта и замените путь на абсолютный:

```json
{
  "servers": {
    "ewb512": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

## Factory Droid

Droid использует формат плагинов Claude Code:

```bash
droid plugin marketplace add "$EWB_HOME"
droid plugin install ewb512-schematics@ewb512-plugins
```

После публикации:

```bash
droid plugin marketplace add https://github.com/OWNER/REPO
droid plugin install ewb512-schematics@ewb512-plugins
```

## Qoder

```bash
cd "$EWB_HOME"
qoder plugins validate . --strict
qoder plugins install .
qoder plugins list
```

Qoder читает `.claude-plugin/plugin.json` и `.mcp.json`. Если ваша версия
Qoder требует другой манифест, используйте ручное подключение MCP-сервера из
следующего раздела.

## Claude Desktop, Windsurf, Cline, Continue, Zed

Эти клиенты не обязаны понимать плагинные манифесты, но все умеют запускать
stdio MCP-сервер. Везде замените `/absolute/path/to/ewb_mcp/scripts/server.py` на свой
путь.

### Claude Desktop

Файл `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

### Windsurf

Файл `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

### Cline

В настройках MCP Cline добавьте сервер:

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

### Continue

Файл `~/.continue/config.yaml`:

```yaml
mcpServers:
  - name: ewb512
    command: python3
    args:
      - /absolute/path/to/ewb_mcp/scripts/server.py
    env:
      EWB_MCP_ALLOW_HOME: "1"
```

### Zed

Файл `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "ewb512": {
      "command": {
        "path": "python3",
        "args": ["/absolute/path/to/ewb_mcp/scripts/server.py"],
        "env": {
          "EWB_MCP_ALLOW_HOME": "1"
        }
      }
    }
  }
}
```

### Универсальный пример

Если клиент принимает стандартный `mcpServers`, подойдёт
`mcp_config.example.json` из корня репозитория:

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOWED_DIRS": "/path/to/schematics:/tmp"
      }
    }
  }
}
```

На Windows разделитель в `EWB_MCP_ALLOWED_DIRS` — `;`.

## Обновление и удаление

Локальная установка из каталога обычно использует ссылку или копию:

- Claude Code: `claude plugin marketplace update ewb512-plugins`, затем
  `claude plugin update ewb512-schematics`.
- Codex: `codex plugin marketplace upgrade ewb512-plugins`, затем
  `codex plugin add ewb512-schematics@ewb512-plugins`.
- Devin: `devin plugins update ewb512-schematics`.
- Muse: `muse plugins update ewb512-schematics`.
- Остальные клиенты: обновите каталог плагина или повторно выполните установку
  из того же источника.

Перед обновлением закоммитьте или скопируйте свои схемы: сервер делает `.bak`
при редактировании, но не управляет версиями пользовательских файлов.

## Что проверить после установки

1. MCP-сервер виден в списке инструментов клиента.
2. Инструмент `ewb_list_parts` возвращает каталог компонентов.
3. `ewb_read_schematic` открывает тестовую схему.
4. `ewb_validate` возвращает `valid: true` и `document_roundtrip_exact: true`
   для файла, созданного самим сервером.
5. Skill `ewb-schematics` доступен агенту.

Если что-то не работает, перейдите к
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).
