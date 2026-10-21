# Changelog

## 1.0.0 — 2026-10-21

Первый публичный выпуск.

- MCP-сервер `server.py` на stdlib без внешних зависимостей: чтение,
  валидация, редактирование, создание и SVG-превью схем EWB 5.x.
- Разбор и побайтовая запись контейнера `.ewb` (`EncryptionType: 2`) и
  документа `Project_5_1`.
- Генерация пустого документа без файла-шаблона, созданного приложением.
- Каталог компонентов EWB, геометрия выводов, автоматическая маршрутизация
  проводов. Полный список всех 40 записей `PartNum 0..39` — в
  `docs/CATALOG.md`.
- Плагинные манифесты и конфигурации для Claude Code, Codex, Cursor,
  Gemini CLI, Qwen Code, OpenCode, Kimi Code, Muse, Antigravity, Devin CLI,
  Hermes Agent, GitHub Copilot CLI, VS Code, Factory Droid и Qoder.
- Локальные маркетплейсы Claude Code, Codex и Muse; переносимый пакет
  Agent Plugins 1.0.0 (`plugin.json` + `mcp.json` + `skills/`).
- Инструкция для агентов `skills/ewb-schematics/SKILL.md`.
- Русская документация: установка, инструменты, формат и диагностика.
- Модульные тесты, включая проверку согласованности всех манифестов, и CI для
  Python 3.8, 3.10, 3.12 и 3.13.
