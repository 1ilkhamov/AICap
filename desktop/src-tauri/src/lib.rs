use std::sync::OnceLock;
use std::path::PathBuf;
use tauri::{
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, Runtime, WindowEvent,
};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;
use std::sync::Mutex;
use rand::RngCore;
use regex::Regex;
use std::io::Write;

const DEFAULT_API_URL: &str = "http://127.0.0.1:1455";

// API base URL - can be overridden via environment variable
fn is_allowed_release_url(url: &str) -> bool {
    const LOCALHOST_PREFIX: &str = "http://localhost:";
    const LOOPBACK_PREFIX: &str = "http://127.0.0.1:";
    let port_str = if let Some(rest) = url.strip_prefix(LOCALHOST_PREFIX) {
        rest
    } else if let Some(rest) = url.strip_prefix(LOOPBACK_PREFIX) {
        rest
    } else {
        return false;
    };

    if port_str.is_empty() || !port_str.chars().all(|c| c.is_ascii_digit()) {
        return false;
    }

    match port_str.parse::<u16>() {
        Ok(port) if port != 0 => true,
        _ => false,
    }
}

fn get_api_base() -> String {
    let default = DEFAULT_API_URL.to_string();
    let Ok(override_url) = std::env::var("AICAP_API_URL") else {
        return default;
    };

    if cfg!(debug_assertions) {
        return override_url;
    }

    if is_allowed_release_url(&override_url) {
        override_url
    } else {
        default
    }
}

// Per-launch API token shared with backend
static API_TOKEN: OnceLock<String> = OnceLock::new();

fn generate_api_token() -> String {
    let mut bytes = [0u8; 32];
    let mut rng = rand::rngs::OsRng;
    rng.fill_bytes(&mut bytes);

    let mut token = String::with_capacity(64);
    for byte in bytes {
        use std::fmt::Write;
        write!(&mut token, "{:02x}", byte).expect("Failed to encode API token");
    }
    token
}

fn get_api_token() -> &'static str {
    API_TOKEN.get_or_init(generate_api_token).as_str()
}

// Reusable HTTP client with proper configuration
static HTTP_CLIENT: OnceLock<reqwest::Client> = OnceLock::new();

// Compiled regex for account_id validation (8 lowercase hex chars)
static ACCOUNT_ID_REGEX: OnceLock<Regex> = OnceLock::new();

// Backend process handle
static BACKEND_PROCESS: OnceLock<Mutex<Option<CommandChild>>> = OnceLock::new();

// Token file path for cleanup
static TOKEN_FILE_PATH: OnceLock<Mutex<Option<PathBuf>>> = OnceLock::new();

/// Validates that account_id matches expected format: exactly 8 lowercase hex characters.
/// This matches the backend's uuid.uuid4()[:8] format used in credentials.py.
fn validate_account_id(account_id: &str) -> Result<(), String> {
    let re = ACCOUNT_ID_REGEX.get_or_init(|| {
        Regex::new(r"^[0-9a-f]{8}$").expect("Invalid regex pattern")
    });
    if re.is_match(account_id) {
        Ok(())
    } else {
        Err(format!("Invalid account_id format: expected 8 lowercase hex characters, got '{}'", account_id))
    }
}

fn get_client() -> &'static reqwest::Client {
    HTTP_CLIENT.get_or_init(|| {
        let mut headers = reqwest::header::HeaderMap::new();
        let token = get_api_token();
        headers.insert(
            reqwest::header::HeaderName::from_static("x-aicap-token"),
            reqwest::header::HeaderValue::from_str(token).expect("Invalid API token"),
        );

        reqwest::Client::builder()
            .default_headers(headers)
            .timeout(std::time::Duration::from_secs(30))
            .connect_timeout(std::time::Duration::from_secs(10))
            .pool_max_idle_per_host(2)
            .build()
            .expect("Failed to create HTTP client")
    })
}

/// Writes the API token to a temp file and returns the file path.
/// On Unix, restricts permissions to 0600. On Windows, relies on temp dir ACLs.
fn write_token_file(token: &str) -> Result<PathBuf, String> {
    let temp_dir = std::env::temp_dir();
    
    // Generate cryptographically random filename to prevent prediction attacks
    let mut rng = rand::rngs::OsRng;
    let mut random_bytes = [0u8; 16];
    rng.fill_bytes(&mut random_bytes);
    let filename = format!("aicap-token-{}.txt", 
        random_bytes.iter().map(|b| format!("{:02x}", b)).collect::<String>());
    let token_path = temp_dir.join(filename);

    // Create file atomically with O_EXCL to prevent symlink/collision attacks
    // On Unix, set mode 0o600 at creation time
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    
    let mut file = options.open(&token_path)
        .map_err(|e| format!("Failed to create token file: {}", e))?;

    file.write_all(token.as_bytes())
        .map_err(|e| format!("Failed to write token to file: {}", e))?;

    file.flush()
        .map_err(|e| format!("Failed to flush token file: {}", e))?;

    Ok(token_path)
}

/// Removes the token file if it exists.
fn cleanup_token_file() {
    let token_guard = TOKEN_FILE_PATH.get_or_init(|| Mutex::new(None));
    if let Ok(mut token_path) = token_guard.lock() {
        if let Some(path) = token_path.take() {
            let _ = std::fs::remove_file(&path);
            println!("Token file cleaned up");
        }
    }
}

fn start_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let backend_guard = BACKEND_PROCESS.get_or_init(|| Mutex::new(None));
    let mut backend = backend_guard.lock().map_err(|e: std::sync::PoisonError<_>| e.to_string())?;
    
    // Already running
    if backend.is_some() {
        return Ok(());
    }

    // Write token to temp file
    let token = get_api_token();
    let token_path = write_token_file(token)?;
    let token_path_str = token_path.to_string_lossy().to_string();

    // Store path for cleanup
    let token_guard = TOKEN_FILE_PATH.get_or_init(|| Mutex::new(None));
    if let Ok(mut stored_path) = token_guard.lock() {
        *stored_path = Some(token_path);
    }
    
    // Try to spawn the sidecar
    match app.shell().sidecar("aicap-backend") {
        Ok(cmd) => {
            let cmd = cmd.env("AICAP_API_TOKEN_FILE", &token_path_str);
            match cmd.spawn() {
                Ok((_, child)) => {
                    *backend = Some(child);
                    println!("Backend started successfully");
                    Ok(())
                }
                Err(e) => {
                    println!("Failed to spawn backend: {}", e);
                    // Clean up token file since backend didn't start
                    cleanup_token_file();
                    // Not fatal - backend might be running externally
                    Ok(())
                }
            }
        }
        Err(e) => {
            println!("Sidecar not found (dev mode?): {}", e);
            // Clean up token file since backend didn't start
            cleanup_token_file();
            // Not fatal in dev mode
            Ok(())
        }
    }
}

fn stop_backend() {
    if let Some(backend_guard) = BACKEND_PROCESS.get() {
        if let Ok(mut backend) = backend_guard.lock() {
            if let Some(child) = backend.take() {
                // Give backend time for graceful shutdown
                std::thread::sleep(std::time::Duration::from_millis(100));
                let _ = child.kill();
                println!("Backend stopped");
            }
        }
    }
    // Clean up token file
    cleanup_token_file();
}

#[tauri::command]
async fn fetch_limits() -> Result<serde_json::Value, String> {
    let api_base = get_api_base();
    let resp = get_client()
        .get(format!("{}/api/v1/limits", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("API error {}: {}", status, detail));
    }

    resp.json().await.map_err(|e| format!("Parse error: {}", e))
}

#[tauri::command]
async fn refresh_limits() -> Result<serde_json::Value, String> {
    let api_base = get_api_base();
    let resp = get_client()
        .post(format!("{}/api/v1/limits/refresh", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("API error {}: {}", status, detail));
    }

    resp.json().await.map_err(|e| format!("Parse error: {}", e))
}


#[tauri::command]
async fn login_openai() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .get(format!("{}/api/v1/auth/openai/login", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Login failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn login_antigravity() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .get(format!("{}/api/v1/auth/antigravity/login", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Login failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn add_account_openai() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .get(format!("{}/api/v1/auth/openai/login?add_account=true", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Add account failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn add_account_antigravity() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .get(format!("{}/api/v1/auth/antigravity/login?add_account=true", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Add account failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn logout_openai() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .post(format!("{}/api/v1/auth/openai/logout", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Logout failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn logout_antigravity() -> Result<(), String> {
    let api_base = get_api_base();
    let resp = get_client()
        .post(format!("{}/api/v1/auth/antigravity/logout", api_base))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Logout failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn get_accounts(provider: Option<String>) -> Result<serde_json::Value, String> {
    let api_base = get_api_base();
    let url = match provider {
        Some(p) => format!("{}/api/v1/accounts?provider={}", api_base, urlencoding::encode(&p)),
        None => format!("{}/api/v1/accounts", api_base),
    };
    let resp = get_client()
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("API error {}: {}", status, detail));
    }

    resp.json().await.map_err(|e| format!("Parse error: {}", e))
}

#[tauri::command]
async fn activate_account(account_id: String) -> Result<(), String> {
    validate_account_id(&account_id)?;
    let api_base = get_api_base();
    let resp = get_client()
        .post(format!("{}/api/v1/accounts/{}/activate", api_base, account_id))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Activate failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn update_account_name(account_id: String, name: String) -> Result<(), String> {
    validate_account_id(&account_id)?;
    let api_base = get_api_base();
    let resp = get_client()
        .put(format!("{}/api/v1/accounts/{}/name?name={}", api_base, account_id, urlencoding::encode(&name)))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Update failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn delete_account(account_id: String) -> Result<(), String> {
    validate_account_id(&account_id)?;
    let api_base = get_api_base();
    let resp = get_client()
        .delete(format!("{}/api/v1/accounts/{}", api_base, account_id))
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(String::from))
            .unwrap_or(body);
        return Err(format!("Delete failed {}: {}", status, detail));
    }
    Ok(())
}

#[tauri::command]
async fn check_backend() -> Result<bool, String> {
    let api_base = get_api_base();
    match get_client()
        .get(format!("{}/health", api_base))
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
fn get_autostart_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    use tauri_plugin_autostart::ManagerExt;
    app.autolaunch()
        .is_enabled()
        .map_err(|e| format!("Failed to check autostart: {}", e))
}

#[tauri::command]
fn set_autostart_enabled(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;
    let autostart = app.autolaunch();
    
    if enabled {
        autostart.enable().map_err(|e| format!("Failed to enable autostart: {}", e))
    } else {
        autostart.disable().map_err(|e| format!("Failed to disable autostart: {}", e))
    }
}

fn toggle_window<R: Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let is_visible = window.is_visible().unwrap_or(false);
        let is_minimized = window.is_minimized().unwrap_or(false);

        if is_visible && !is_minimized {
            let _ = window.hide();
        } else {
            if is_minimized {
                let _ = window.unminimize();
            }
            // Position near tray (bottom right)
            if let Ok(Some(monitor)) = window.primary_monitor() {
                let size = monitor.size();
                let scale = monitor.scale_factor();
                let x = ((size.width as f64 / scale) - 380.0) as i32;
                let y = ((size.height as f64 / scale) - 530.0) as i32;
                let _ = window.set_position(tauri::Position::Logical(tauri::LogicalPosition {
                    x: x as f64,
                    y: y as f64,
                }));
            }
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // Start backend sidecar
            let _ = start_backend(app.handle());
            
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("AICap")
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_window(tray.app_handle());
                    }
                })
                .build(app)?;

            if let Some(window) = app.get_webview_window("main") {
                let window_clone = window.clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = window_clone.hide();
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|_window, event| {
            // Stop backend when app is closing
            if let WindowEvent::Destroyed = event {
                stop_backend();
            }
        })
        .invoke_handler(tauri::generate_handler![
            fetch_limits,
            refresh_limits,
            login_openai,
            login_antigravity,
            add_account_openai,
            add_account_antigravity,
            logout_openai,
            logout_antigravity,
            get_accounts,
            activate_account,
            update_account_name,
            delete_account,
            check_backend,
            get_autostart_enabled,
            set_autostart_enabled
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
