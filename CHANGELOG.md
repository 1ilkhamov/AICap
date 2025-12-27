# Changelog / История изменений

[English](#english) | [Русский](#русский)

---

## English

### [1.1.0] - 2024-12-28

#### Added
- One-click installation: backend starts automatically with desktop app
- Sidecar architecture: backend bundled as executable inside installer
- Build scripts for Windows (`build.ps1`) and Linux/macOS (`build.sh`)

#### Changed
- Project renamed from "AI Limits Tracker" to "AICap"
- Credential storage moved to `~/.aicap/`
- Environment variable renamed to `AICAP_API_URL`

### [1.0.0] - 2024-12-28

#### Added
- OAuth 2.0 authentication with PKCE for OpenAI/Codex
- Real-time usage tracking (5-hour and weekly windows)
- System tray application with popup dashboard
- Auto-refresh every 5 minutes
- Encrypted local token storage (PBKDF2 + Fernet)
- Rate limiting protection (60 req/min)
- Desktop notifications at 80% usage
- Auto-start with Windows
- Localization (English, Russian)
- Multi-account management
- Export data (JSON/CSV)

#### Security
- CSRF protection via HMAC-signed state tokens
- Content Security Policy in desktop app
- Secure credential storage with machine-bound encryption

---

## Русский

### [1.1.0] - 2024-12-28

#### Добавлено
- Установка в один клик: backend запускается автоматически с приложением
- Sidecar архитектура: backend встроен в установщик как исполняемый файл
- Скрипты сборки для Windows (`build.ps1`) и Linux/macOS (`build.sh`)

#### Изменено
- Проект переименован из "AI Limits Tracker" в "AICap"
- Хранение учётных данных перенесено в `~/.aicap/`
- Переменная окружения переименована в `AICAP_API_URL`

### [1.0.0] - 2024-12-28

#### Добавлено
- OAuth 2.0 авторизация с PKCE для OpenAI/Codex
- Отслеживание в реальном времени (5-часовые и недельные окна)
- Приложение в системном трее с popup панелью
- Автообновление каждые 5 минут
- Зашифрованное хранение токенов (PBKDF2 + Fernet)
- Rate limiting (60 запросов/мин)
- Уведомления при 80% использования
- Автозапуск с Windows
- Локализация (English, Русский)
- Управление несколькими аккаунтами
- Экспорт данных (JSON/CSV)

#### Безопасность
- CSRF защита через HMAC-подписанные state токены
- Content Security Policy в desktop приложении
- Безопасное хранение с привязкой к машине

---

## Planned / Планируется

- Anthropic Claude support / Поддержка Anthropic Claude
- Google AI support / Поддержка Google AI
- Usage history persistence / Сохранение истории использования
