# AICap

[English](#english) | [Русский](#русский)

---

## English

Track your AI service usage limits in real-time from the system tray.

### Features

- 🔐 OAuth authentication with OpenAI/Codex (PKCE)
- 📊 Real-time usage tracking (5-hour and weekly windows)
- 🖥️ Beautiful system tray popup
- 🔄 Auto-refresh every 5 minutes
- 🔒 Encrypted local token storage
- ⚡ Rate limiting protection
- 🔔 Desktop notifications at 80% usage
- 🚀 Auto-start with Windows
- 🌐 Localization (English, Russian)

### Installation

#### Prerequisites

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node.js 20+** — [nodejs.org](https://nodejs.org/)
- **Rust** — [rustup.rs](https://rustup.rs/)

#### Build from Source

**Windows:**
```powershell
git clone https://github.com/1ilkhamov/AICap.git
cd AICap
.\build.ps1
```

**Linux/macOS:**
```bash
git clone https://github.com/1ilkhamov/AICap.git
cd AICap
chmod +x build.sh && ./build.sh
```

After build completes, find the installer in:
- **Windows:** `desktop/src-tauri/target/release/bundle/nsis/AICap_1.1.0_x64-setup.exe`
- **macOS:** `desktop/src-tauri/target/release/bundle/dmg/`
- **Linux:** `desktop/src-tauri/target/release/bundle/deb/` or `appimage/`

### Usage

1. Launch AICap (backend starts automatically)
2. Click the tray icon to open the dashboard
3. Connect your OpenAI account
4. View your usage limits
5. Enable "Start with Windows" in Settings

### Data Storage

Credentials stored securely in `~/.aicap/` (outside app folder), encrypted with PBKDF2 (480k iterations).

### Supported Services

- ✅ OpenAI Codex (Team/Pro)
- 🔜 Anthropic Claude
- 🔜 Google AI

---

## Русский

Отслеживайте лимиты AI-сервисов в реальном времени из системного трея.

### Возможности

- 🔐 OAuth авторизация с OpenAI/Codex (PKCE)
- 📊 Отслеживание в реальном времени (5-часовые и недельные окна)
- 🖥️ Красивый popup в системном трее
- 🔄 Автообновление каждые 5 минут
- 🔒 Зашифрованное хранение токенов
- ⚡ Защита от превышения лимитов
- 🔔 Уведомления при 80% использования
- 🚀 Автозапуск с Windows
- 🌐 Локализация (English, Русский)

### Установка

#### Требования

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node.js 20+** — [nodejs.org](https://nodejs.org/)
- **Rust** — [rustup.rs](https://rustup.rs/)

#### Сборка из исходников

**Windows:**
```powershell
git clone https://github.com/1ilkhamov/AICap.git
cd AICap
.\build.ps1
```

**Linux/macOS:**
```bash
git clone https://github.com/1ilkhamov/AICap.git
cd AICap
chmod +x build.sh && ./build.sh
```

После сборки установщик будет в:
- **Windows:** `desktop/src-tauri/target/release/bundle/nsis/AICap_1.1.0_x64-setup.exe`
- **macOS:** `desktop/src-tauri/target/release/bundle/dmg/`
- **Linux:** `desktop/src-tauri/target/release/bundle/deb/` или `appimage/`

### Использование

1. Запустите AICap (backend запустится сам)
2. Нажмите на иконку в трее
3. Подключите аккаунт OpenAI
4. Смотрите лимиты
5. Включите "Запуск с Windows" в Настройках

### Хранение данных

Учётные данные в `~/.aicap/` (вне папки приложения), зашифрованы PBKDF2 (480k итераций).

### Поддерживаемые сервисы

- ✅ OpenAI Codex (Team/Pro)
- 🔜 Anthropic Claude
- 🔜 Google AI

---

## Development

```bash
# Backend
cd backend && python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 1455 --reload

# Desktop (requires Rust + Node.js)
cd desktop && npm install && npm run tauri dev

# Tests
cd backend && pytest tests/ -v
```

### Backend-Desktop Security

- **Token Authentication**: Desktop app passes API token via temporary file (`AICAP_API_TOKEN_FILE` env variable). Token authentication is required when binding to non-loopback addresses.
- **OAuth State**: One-time use state tokens are provider-routed for enhanced security.
- **Dev Mode**: `AICAP_DEV_MODE=true` enables CORS for localhost development only. Do not use in production.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, PyInstaller
- **Desktop**: Tauri 2, TypeScript, Vite
- **Auth**: OAuth 2.0 + PKCE

## License

MIT
