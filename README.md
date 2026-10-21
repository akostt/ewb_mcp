# EWB 5.12 MCP — чтение, редактирование и создание схем

MCP-сервер для файлов Electronics Workbench 5.x (`.ewb`). Он читает схему,
показывает компоненты, выводы и связи, проверяет структуру, редактирует
элементы и провода, создаёт новые файлы и строит SVG-превью.

Формат восстановлен реверс-инжинирингом установщика и реальных файлов EWB.
Сама EWB не устанавливается и не запускается. Сервер не содержит кода,
ресурсов или бинарников EWB.

Пакет устанавливается как плагин в основные AI-среды и подключается к любому
MCP-клиенту вручную. Общая логика и skills лежат в корне, а для каждого
клиента добавлен тонкий манифест.

## Возможности

- Чтение `.ewb` без EWB: компоненты, позиции, значения, выводы, провода, цепи.
- Создание новых схем в формате EWB 5.12.
- Добавление, перемещение, поворот, переименование и удаление компонентов.
- Добавление, удаление и переразводка проводов.
- Проверка контейнера, документа, индексов, выводов, маршрутов и контрольной
  суммы.
- SVG-превью для быстрой визуальной проверки.
- Атомарная запись и резервная копия `.bak` перед изменением.
- Политика разрешённых каталогов.
- Ноль внешних зависимостей Python.

## Требования

- Python 3.8 или новее, команда `python3` в `PATH`.
- Внешние Python-пакеты не нужны.
- EWB устанавливать не требуется.

## Быстрый старт

```bash
cd /path/to/ewb_mcp
python3 -m unittest discover -s tests -v
```

Проверка запуска сервера:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}' \
  | python3 scripts/server.py
```

В ответе должно быть `"name": "ewb512-schematic"`.

## Установка

Подробные команды, конфигурации и пути для каждого клиента — в
[`docs/INSTALL.md`](docs/INSTALL.md). Ниже сводная таблица.

| Среда | Манифест / конфигурация | Установка |
|---|---|---|
| Claude Code | `.claude-plugin/`, `.mcp.json` | `/plugin marketplace add /path/to/ewb_mcp`, затем `/plugin install ewb512-schematics@ewb512-plugins` |
| Codex | `.agents/plugins/marketplace.json`, `.codex-plugin/`, `mcp.json` | `codex plugin marketplace add "$PWD"`, затем `codex plugin add ewb512-schematics@ewb512-plugins` |
| Cursor | `.cursor-plugin/plugin.json` | `/add-plugin /path/to/ewb_mcp` или Customize → Plugins |
| Gemini CLI | `gemini-extension.json`, `GEMINI.md` | `gemini extensions install "$PWD"` |
| Qwen Code | `gemini-extension.json`, `GEMINI.md` | `qwen extensions install "$PWD"` |
| OpenCode | ручная конфигурация | [`.opencode/INSTALL.md`](.opencode/INSTALL.md) |
| Kimi Code | `.kimi-plugin/plugin.json` | `/plugins install /path/to/ewb_mcp` |
| Muse | `.muse-plugin/plugin.json`, marketplace | `muse plugins install "$PWD"` |
| Antigravity | `.antigravity-plugin/plugin.json`, `mcp_config.json` | `agy plugin install /path/to/ewb_mcp` |
| Devin CLI | `.devin-plugin/plugin.json` | `devin plugins install --local "$PWD"` |
| Hermes Agent | `plugin.json`, `mcp.json`, `skills/` | `hermes plugins install /path/to/ewb_mcp --enable` |
| GitHub Copilot CLI | `.claude-plugin/` | `copilot plugin marketplace add "$PWD"` |
| VS Code | `.vscode/mcp.json` | открыть каталог и запустить `ewb512` в панели MCP |
| Factory Droid | `.claude-plugin/` | `droid plugin marketplace add "$PWD"` |
| Qoder | `.claude-plugin/` | `qoder plugins install .` |
| Claude Desktop, Windsurf, Cline, Continue, Zed | стандартный `mcpServers` | см. `docs/INSTALL.md` |

После публикации репозитория вместо локального пути можно указывать
`OWNER/REPO`. В документации такие места обозначены явно.

### Как устроена мультиклиентная упаковка

- `plugin.json` + `mcp.json` + `skills/` — переносимый пакет Agent Plugins
  1.0.0. Его понимают Codex, Hermes и другие среды.
- `.claude-plugin/` — Claude Code, GitHub Copilot CLI, Factory Droid, Qoder.
- `.codex-plugin/` и `.agents/plugins/marketplace.json` — Codex App и CLI.
- `.cursor-plugin/` — Cursor; используется `${CURSOR_PLUGIN_ROOT}`, потому что
  Cursor не раскрывает `${PLUGIN_ROOT}`.
- `.devin-plugin/` — Devin; MCP-сервер объявлен inline, чтобы не использовался
  корневой `.mcp.json` с переменной Claude.
- `.kimi-plugin/` — Kimi Code; skills, `sessionStart` и MCP-сервер.
- `.muse-plugin/` — Muse; MCP-сервер запускается через
  `scripts/ewb_mcp_launcher.py`, так как Muse не передаёт `env` в манифесте.
- `.antigravity-plugin/` + `mcp_config.json` — Antigravity.
- `gemini-extension.json` — Gemini CLI и Qwen Code.
- `.vscode/mcp.json` — VS Code / GitHub Copilot в режиме агента.
- `mcp_config.example.json` — универсальный пример для остальных клиентов.

Все конфигурации указывают на один и тот же `scripts/server.py`. Дублирования кода
нет.

### Ручное подключение

Любой клиент, поддерживающий stdio MCP, можно подключить так:

```json
{
  "mcpServers": {
    "ewb512": {
      "command": "python3",
      "args": ["/path/to/ewb_mcp/scripts/server.py"],
      "env": {
        "EWB_MCP_ALLOW_HOME": "1"
      }
    }
  }
}
```

`EWB_MCP_ALLOW_HOME` добавляет домашний каталог. Для более строгой политики
замените его на явный список:

```json
"env": {
  "EWB_MCP_ALLOWED_DIRS": "/path/to/schematics:/tmp"
}
```

На Windows разделитель — `;`.

Сервер общается через stdio по JSON-RPC 2.0: построчный формат, также
поддерживается `Content-Length`. Сообщения протокола идут в stdout, служебный
лог — в stderr.

## Инструменты

| Инструмент | Назначение | Основные аргументы |
|---|---|---|
| `ewb_list_parts` | Каталог компонентов: PartNum, имя, число выводов, известные повороты | `query`, `only_with_pins`, `include_rotations` |
| `ewb_read_schematic` | Прочитать компоненты, выводы, провода, цепи и предупреждения | `path`, `include_pins`, `include_wires`, `include_nets`, `include_text` |
| `ewb_render_svg` | Построить SVG-превью | `path`, `output_path`, `width`, `height`, `inline` |
| `ewb_create_schematic` | Создать новый `.ewb` сразу с компонентами и проводами | `path`, `overwrite`, `description`, `components`, `wires` |
| `ewb_add_component` | Добавить компонент | `path`, `part`, `x`, `y`, `rotation`, `ref`, `value`, `model` |
| `ewb_add_wire` | Соединить два вывода | `path`, `from`, `from_pin`, `to`, `to_pin`, `route`, `node`, `colour` |
| `ewb_update_component` | Переместить, повернуть, переименовать, изменить значение | `path`, `index` или `ref`, `x`, `y`, `rotation`, `refid`, `value`, `model` |
| `ewb_update_wire` | Изменить маршрут, метку, цвет или id провода | `path`, `index`, `route`, `node`, `colour`, `wire_id` |
| `ewb_remove_component` | Удалить компонент и связанные провода | `path`, `index` или `ref`, `remove_wires` |
| `ewb_remove_wire` | Удалить провод по индексу | `path`, `index` |
| `ewb_validate` | Проверить контейнер, документ, элементы, выводы, маршруты и checksum | `path` |

Полное описание аргументов и ответов — в [`docs/TOOLS.md`](docs/TOOLS.md).

## Каталог компонентов

Сервер поддерживает все **40 записей библиотеки EWB 5.12** — `PartNum` от 0
до 39. Это источники напряжения и тока AC/DC, батарея, резистор, конденсатор,
катушка индуктивности, трансформатор, диоды, стабилитрон, светодиод, лампа,
предохранитель, реле, биполярные транзисторы, JFET, MOSFET, операционный
усилитель, амперметр, вольтметр, соединитель, земля, переключатели,
управляемые источники и узел.

Полная таблица с именами, префиксами, описаниями, числом выводов и
доступными поворотами — в [`docs/CATALOG.md`](docs/CATALOG.md). Машинный
каталог с точными смещениями выводов возвращает `ewb_list_parts`.

Все 40 записей можно добавлять через `ewb_add_component` и
`ewb_create_schematic`. Для 17 из них восстановлена геометрия выводов, поэтому
работает автоматическая маршрутизация проводов. Для остальных компонент
создаётся и читается, но провод сохраняется без явного маршрута `segs`; сервер
предупреждает об этом. Блоки `Instrument` и `ExtComp` читаются, но не
создаются.

## Создание схемы

```json
{
  "path": "/path/to/ewb_mcp/local/examples/my_schematic.ewb",
  "overwrite": true,
  "description": "RC + LED",
  "components": [
    {"part": "GROUND", "x": 400, "y": 620},
    {"part": "GROUND", "x": 730, "y": 620},
    {"part": "BATTERY", "ref": "V1", "x": 400, "y": 500, "value": 9},
    {"part": "RESISTOR", "ref": "R1", "x": 500, "y": 460, "rotation": 1, "value": "1k"},
    {"part": "CAPACITOR", "ref": "C1", "x": 600, "y": 480, "value": "1u"},
    {"part": "LED", "ref": "D1", "x": 700, "y": 480, "rotation": 2}
  ],
  "wires": [
    {"from": "V1", "from_pin": 1, "to": "R1", "to_pin": 0},
    {"from": "R1", "from_pin": 1, "to": "C1", "to_pin": 0},
    {"from": "C1", "from_pin": 1, "to": "D1", "to_pin": 1},
    {"from": "D1", "from_pin": 0, "to": 1, "to_pin": 0},
    {"from": "V1", "from_pin": 0, "to": 0, "to_pin": 0}
  ]
}
```

В `wires` поля `from`/`to` могут быть индексом компонента в этом же вызове или
его `ref`. Число `1` — индекс второй земли; строка `"2"` означала бы RefID
`"2"`. Если `ref` не задан, сервер генерирует обозначение.

Значения можно передавать числом или строкой с суффиксом `p`, `n`, `u`, `m`,
`k`, `M`, `meg`, `G`:

```json
{"part": "RESISTOR", "value": "4k7"}
```

Регистр важен: `m` — милли, `M` — мега.

Каталог `local/` не входит в git и в распространяемый пакет. Пример
`local/examples/rc_led.ewb` создаётся сервером и служит только локальной
проверкой; при необходимости его можно сгенерировать заново.

## Чтение и проверка

```json
{"path": "local/examples/лаба 4.ewb", "include_nets": true}
```

`ewb_read_schematic` возвращает:

- `elements` — индекс, `PartNum`, имя, `refid`, позицию, поворот, значение,
  модель и абсолютные координаты выводов;
- `wires` — индексы элементов на концах, номера выводов, метку, цвет и
  сегменты маршрута;
- `nets` — электрические узлы, построенные по проводам;
- `errors` и `warnings` — структурные замечания.

`ewb_validate` возвращает `valid`, `errors`, `warnings`, `checks`, `details` и
`counts`. Ошибки означают, что файл повреждён или его нельзя безопасно
редактировать. Предупреждения не блокируют работу.

Ключевые флаги:

- `document_roundtrip_exact` — документ воспроизводится байт-в-байт;
- `container_roundtrip_exact` — контейнер собирается повторно;
- `checksum_matches` — контрольная сумма соответствует документу.

## Редактирование

Все изменяющие инструменты работают с существующим файлом и сохраняют его в
формате EWB 5.12. Запись атомарная, предыдущая версия сохраняется рядом как
`<имя>.ewb.bak`.

Типичный порядок:

1. `ewb_read_schematic` или `ewb_validate` — посмотреть индексы и выводы.
2. `ewb_update_component` / `ewb_add_component` — изменить состав.
3. `ewb_add_wire` / `ewb_update_wire` — соединить или переразвести.
4. `ewb_validate` — проверить результат.
5. `ewb_render_svg` — посмотреть превью.

Если компонент двигают или поворачивают, подключённые провода переразводятся
автоматически, когда геометрия выводов известна. Для неизвестной геометрии
провод остаётся без `segs`, и EWB сама прокладывает его при открытии.

У всех земляных символов `refid` равен `"0"`. Для конкретной земли используйте
`index`, а не `ref`. Строка `"2"` в `ref` — это обозначение `2`, а не индекс.

## Формат

Кратко:

- Контейнер: текстовый заголовок с CRLF, `EncryptionType: 2`, пара-кодирование,
  блоки по 1024 байта со сжатием в стиле PKWARE implode, checksum.
- Документ: текст `Project_5_1` с CRLF, дерево блоков `Block`/`Document`.
- Элементы: `Comp`, `Instrument`, `ExtComp`; поля `PartNum`, `Position`,
  `Value`, `ModelUnits`, `ModelName`, `Status`, `Common/RefID`.
- Провода: `pos a pa b pb`, необязательные `segs`, `colour`, `wire_id`,
  `node_p`, `x_factor`, `y_factor`.
- Вывод: `Position + offset(PartNum, rotation, pin)`.
- Коды направлений: 1 = +x, 2 = +y, 4 = -x, 8 = -y; 3, 6, 9, 12 — диагонали.

Подробное описание с примерами и ограничениями — в
[`docs/FORMAT.md`](docs/FORMAT.md).

### Почему нет `blank_template.ewb`

Пустой документ генерируется кодом в `scripts/ewb_blank.py`: `CircuitHeader`,
`Preferences`, пустые `Elements` и `Wires`. Остальные необязательные блоки
EWB инициализирует своими значениями при открытии или сохранении. Поэтому в
пакете нет файла-шаблона, созданного приложением.

### Совместимость контейнера

Пересжатие контейнера не обязано совпадать с исходным файлом побайтно: EWB
допускает разные корректные варианты сжатия. Поэтому
`container_roundtrip_exact` может быть `false`, пока документ читается и
checksum совпадает. Для редактирования важно
`document_roundtrip_exact: true`; если он `false`, сервер отказывается
записывать файл.

## Политика путей и безопасность

По умолчанию разрешены:

- текущий рабочий каталог;
- каталог проекта `ewb_mcp`;
- `/tmp` и `/private/tmp`;
- каталоги из `EWB_MCP_ALLOWED_DIRS`.

Дополнительно:

- `EWB_MCP_ALLOW_HOME=1` добавляет домашний каталог. Флаг включён в плагинных
  конфигурациях, потому что плагин может запускаться со своим рабочим
  каталогом.
- Для строгой изоляции уберите флаг и задайте явный `EWB_MCP_ALLOWED_DIRS`.

Пути вне списка отклоняются. Символическая ссылка, ведущая за пределы
разрешённого каталога, также отклоняется после `Path.resolve`. Расширение
должно быть `.ewb` для схем и `.svg` для превью.

Сервер:

- не запускает EWB;
- не использует сеть;
- не устанавливает пакеты;
- пишет только в разрешённые каталоги;
- делает `.bak` перед изменением;
- не перезаписывает исходный файл, если путь не передан явно.

## Проверка

На реальном файле `local/examples/лаба 4.ewb`:

- прочитано 97 элементов и 98 проводов;
- `ewb_validate`: `valid: true`, 0 ошибок, 0 предупреждений;
- `document_roundtrip_exact: true`, `checksum_matches: true`;
- добавление, перемещение и удаление компонента и провода проходят без ошибок;
- исходный файл не изменялся; резервная копия `.bak` создаётся.

На схеме из тестов:

- 6 элементов, 5 проводов, 5 цепей;
- `valid: true`, все три проверки `checks` — `true`.

Тест исходной схемы пропускается, если файла нет: пример не поставляется в
репозитории.

### Статус проверки манифестов

JSON-манифесты и их согласованность проверяются модульными тестами. Команды
установки взяты из документации соответствующих клиентов. Полный запуск
плагина внутри каждого стороннего клиента не выполнялся: эти клиенты не
установлены в окружении разработки. Если клиент меняет формат манифеста,
используйте ручное подключение через `mcpServers` — оно работает независимо
от плагинной упаковки.

## Разработка и тесты

```bash
cd /path/to/ewb_mcp
python3 -m unittest discover -s tests -v
```

Тесты проверяют:

- побайтовый round-trip пустого документа и контейнера;
- сжатие и распаковку блоков;
- создание, чтение и правку схемы;
- резервные копии и политику путей;
- SVG-превью;
- согласованность всех плагинных манифестов;
- исходную схему из `local/examples/`, если она есть.

CI в `.github/workflows/tests.yml` запускает набор на Python 3.8, 3.10, 3.12
и 3.13. Правила участия — в `CONTRIBUTING.md`, история версий — в
`CHANGELOG.md`.

## Ограничения

- Поддерживается только `EncryptionType: 2`.
- Нет симуляции, расчёта цепей и электрического ERC: проверяется структура
  файла, индексы, выводы, маршруты и checksum.
- SVG — приблизительное превью, а не точная копия отрисовки EWB. В плотных
  схемах подписи могут пересекаться.
- Значения многих компонентов состоят из нескольких полей. В превью
  показывается только первое; остальные сохраняются.
- Каталог содержит 40 записей `PartNum` 0..39; полный список —
  [`docs/CATALOG.md`](docs/CATALOG.md).
- Для 17 записей каталога восстановлена геометрия выводов. Для остальных
  компонентов и поворотов она не наблюдалась: такие элементы можно читать и
  создавать, но автоматическая переразводка проводов для них ограничена.
- `ExtComp` и `Instrument` читаются, но создание новых инструментов не
  реализовано.
- Проверка открытия файла в самой EWB не выполнялась: по условию задачи
  приложение не устанавливалось и не запускалось.

## Совместимость и лицензирование

Код написан с нуля по результатам реверс-инжиниринга формата. В
распространяемом пакете нет исполняемых файлов EWB, её библиотек, ресурсов,
шрифтов или извлечённого шаблона схемы. Пустой документ генерируется
программно из описания полей. Локальный установщик и база IDA лежат только в
игнорируемом каталоге `local/bin/`.

Текстовые имена блоков и полей (`Project_5_1`, `Circuit`, `Elements`, `Wires`,
`Comp`, `wire`, `PartNum`, `Position` и т. п.) необходимы для совместимости
формата и не являются копированием реализации.

Лицензия пакета — MIT, см. `LICENSE`.

## Состав каталога

```text
ewb_mcp/
  scripts/
    server.py                        MCP-сервер и инструменты
    ewb_codec.py                     контейнер .ewb, сжатие, checksum
    ewb_doc.py                       разбор и запись Project_5_1
    ewb_blank.py                     генерация пустого документа
    ewb_parts.py                     каталог, выводы, значения, маршруты
    ewb_svg.py                       SVG-превью
    ewb_mcp_launcher.py              launcher для Muse
  plugin.json                        Agent Plugins 1.0.0
  mcp.json                           MCP для Agent Plugins / Codex / Hermes
  .mcp.json                          MCP для Claude Code
  mcp_config.json                    MCP для Antigravity-плагина
  mcp_config.example.json            универсальный пример
  gemini-extension.json              Gemini CLI / Qwen Code
  .claude-plugin/                    Claude Code, Copilot CLI, Droid, Qoder
  .codex-plugin/                     Codex
  .cursor-plugin/                    Cursor
  .devin-plugin/                     Devin CLI
  .kimi-plugin/                      Kimi Code
  .muse-plugin/                      Muse
  .antigravity-plugin/               Antigravity
  .agents/plugins/marketplace.json   маркетплейс Codex
  .vscode/mcp.json                   VS Code
  .opencode/INSTALL.md               инструкция для OpenCode
  skills/ewb-schematics/SKILL.md     инструкция для агента
  docs/                              установка, каталог, инструменты, формат, диагностика
  docs/CATALOG.md                    все 40 компонентов PartNum 0..39
  tests/test_ewb_mcp.py              модульные тесты
  .github/workflows/tests.yml        CI для Python 3.8–3.13
  AGENTS.md                          контекст для Codex и других агентов
  GEMINI.md                          контекст для Gemini CLI
  CLAUDE.md                          контекст для Claude Code
  CHANGELOG.md                       история версий
  CONTRIBUTING.md                    правила участия
  LICENSE                            MIT
  .gitattributes                     нормализация строк и binary-правила
  .editorconfig                      стиль отступов и окончаний строк
  .gitignore                         правила локального git
  local/                             локальная папка, полностью игнорируется git
```

`ewb_mcp` — отдельный git-репозиторий. Папка `local/` добавлена в
`.gitignore` целиком: её содержимое не попадает в коммиты, но остаётся на
диске и доступно серверу.

Каталог можно переносить целиком. Плагинные конфигурации вычисляют путь к
`scripts/server.py` от корня плагина, а примеры и бинарники лежат в `local/` внутри
каталога.
