import { invoke } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { t, getLocale, setLocale, getAvailableLocales, Locale } from "./i18n";
import "./styles.css";

// App version (loaded from tauri.conf.json)
let appVersion = "1.1.0"; // fallback
getVersion().then(v => appVersion = v).catch(() => {});

// SVG Icons
const icons = {
  bolt: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`,
  calendar: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>`,
  clock: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  refresh: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>`,
  settings: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>`,
  lock: `<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
  plug: `<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/></svg>`,
  alert: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
  bot: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>`,
  rocket: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>`,
  bell: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>`,
  globe: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>`,
  x: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`,
  user: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  pencil: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>`,
  check: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`,
  crown: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/></svg>`,
  star: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  users: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
  plus: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>`,
  trash: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`,
  chevronDown: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`,
  // Google/Antigravity sparkle icon
  sparkles: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M3 5h4"/><path d="M19 17v4"/><path d="M17 19h4"/></svg>`,
  // Gemini model icon  
  gemini: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.93 4.93 2.83 2.83"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/></svg>`,
  // Claude icon
  claude: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M2 12h2"/><path d="M20 12h2"/></svg>`,
  // OpenAI icon
  openai: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/></svg>`,
};


interface LimitsData {
  provider: string;
  is_authenticated: boolean;
  account_id?: string;
  plan_type?: string;
  email?: string;
  primary_used_percent?: number;
  primary_reset_at?: string;
  secondary_used_percent?: number;
  secondary_reset_at?: string;
  models?: ModelQuota[];
  error?: string;
}

interface ModelQuota {
  model_name: string;
  display_name: string;
  remaining_fraction: number;
  used_percent: number;
  reset_time?: string;
}

interface Account {
  id: string;
  provider: string;
  name: string;
  is_active: boolean;
}

type Provider = 'openai' | 'antigravity';

// State
let limitsData: Record<Provider, LimitsData | null> = { openai: null, antigravity: null };
let accounts: Account[] = [];
let currentProvider: Provider = 'openai';
let isLoading = false;
let backendAvailable = false;
let lastNotifiedPrimary = false;
let lastNotifiedSecondary = false;
let settingsOpen = false;
let accountsExpanded = false;
let editingAccountId: string | null = null;
let notificationsEnabled = true;
let autoRefreshEnabled = true;
let isFirstRender = true;

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const NOTIFICATION_THRESHOLD = 80;
const SETTINGS_KEY = 'aicap-settings';
const CACHE_KEY = 'aicap-cache';
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes

const escapeHtml = (value: string): string => value
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/\"/g, "&quot;")
  .replace(/'/g, "&#39;");

const escapeAttr = (value: string): string => escapeHtml(value);

// Cached data interface

interface CachedData {
  limits: Record<Provider, LimitsData | null>;
  accounts: Account[];
  timestamp: number;
  currentProvider: Provider;
}

// Cache management
function saveToCache(limits: Record<Provider, LimitsData | null>, accs: Account[]): void {
  try {
    const data: CachedData = { limits, accounts: accs, timestamp: Date.now(), currentProvider };
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch (e) { console.error("Cache save error:", e); }
}

function loadFromCache(): CachedData | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;
    const data = JSON.parse(cached) as CachedData;
    // Migration: old format had single limitsData
    if (!data.limits || typeof data.limits !== 'object') {
      return null;
    }
    return data;
  } catch { return null; }
}

function isCacheStale(timestamp: number): boolean {
  return Date.now() - timestamp > CACHE_TTL_MS;
}

// Button loading state management
function setButtonLoading(btnId: string, loading: boolean, loadingText?: string): void {
  const btn = document.getElementById(btnId) as HTMLButtonElement | null;
  if (!btn) return;

  if (loading) {
    btn.classList.add('loading');
    btn.setAttribute('disabled', 'true');
    if (loadingText) btn.dataset.originalText = btn.textContent || '';
    if (loadingText) btn.textContent = loadingText;
  } else {
    btn.classList.remove('loading');
    btn.removeAttribute('disabled');
    if (btn.dataset.originalText) {
      btn.textContent = btn.dataset.originalText;
      delete btn.dataset.originalText;
    }
  }
}

// Settings
function loadSettings(): void {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      const settings = JSON.parse(saved);
      notificationsEnabled = settings.notifications ?? true;
      autoRefreshEnabled = settings.autoRefresh ?? true;
    }
  } catch { /* Use defaults */ }
}

function saveSettings(): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    notifications: notificationsEnabled,
    autoRefresh: autoRefreshEnabled,
  }));
}

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// Toast notifications
function showToast(message: string, type: 'success' | 'error' | 'info' = 'success'): void {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const text = document.createElement('span');
  text.textContent = message;
  toast.appendChild(text);
  document.body.appendChild(toast);


  // Trigger animation
  requestAnimationFrame(() => toast.classList.add('show'));

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// Confirmation dialog
function showConfirmDialog(title: string, message: string): Promise<boolean> {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'dialog-overlay';

    // Build dialog DOM safely without innerHTML for dynamic content
    const dialog = document.createElement('div');
    dialog.className = 'dialog';

    const titleEl = document.createElement('div');
    titleEl.className = 'dialog-title';
    titleEl.textContent = title;  // Safe: textContent escapes HTML

    const messageEl = document.createElement('div');
    messageEl.className = 'dialog-message';
    messageEl.textContent = message;  // Safe: textContent escapes HTML

    const actions = document.createElement('div');
    actions.className = 'dialog-actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'dialog-btn dialog-btn-cancel';
    cancelBtn.textContent = t('cancel');

    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'dialog-btn dialog-btn-confirm';
    confirmBtn.textContent = t('confirm');

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    dialog.appendChild(titleEl);
    dialog.appendChild(messageEl);
    dialog.appendChild(actions);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // Trigger animation
    requestAnimationFrame(() => overlay.classList.add('show'));

    const close = (result: boolean) => {
      overlay.classList.remove('show');
      setTimeout(() => overlay.remove(), 200);
      resolve(result);
    };

    cancelBtn.addEventListener('click', () => close(false));
    confirmBtn.addEventListener('click', () => close(true));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
  });
}

// Debounce helper
function debounce<T extends (...args: unknown[]) => unknown>(fn: T, ms: number): T {
  let timeoutId: ReturnType<typeof setTimeout>;
  return ((...args: unknown[]) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), ms);
  }) as T;
}

// Notifications
async function checkAndNotify(data: LimitsData): Promise<void> {
  if (!notificationsEnabled) {
    console.debug("Notifications disabled, skipping");
    return;
  }

  const primaryPercent = data.primary_used_percent ?? 0;
  const secondaryPercent = data.secondary_used_percent ?? 0;

  const shouldNotifyPrimary = primaryPercent >= NOTIFICATION_THRESHOLD && !lastNotifiedPrimary;
  const shouldNotifySecondary = secondaryPercent >= NOTIFICATION_THRESHOLD && !lastNotifiedSecondary;

  // Reset notification flags when usage drops below threshold
  if (primaryPercent < NOTIFICATION_THRESHOLD) lastNotifiedPrimary = false;
  if (secondaryPercent < NOTIFICATION_THRESHOLD) lastNotifiedSecondary = false;

  if (!shouldNotifyPrimary && !shouldNotifySecondary) {
    return;
  }

  try {
    // Check and request permission
    let permissionGranted = await isPermissionGranted();
    console.debug("Notification permission status:", permissionGranted);

    if (!permissionGranted) {
      console.debug("Requesting notification permission...");
      const permission = await requestPermission();
      permissionGranted = permission === "granted";
      console.debug("Permission request result:", permission);
    }

    if (!permissionGranted) {
      console.warn("Notification permission denied");
      return;
    }

    const providerName = data.provider === 'antigravity' ? 'Antigravity' : 'OpenAI';

    // Send notifications
    if (shouldNotifyPrimary) {
      console.debug("Sending primary usage notification:", primaryPercent);
      await sendNotification({
        title: `${providerName}: ${t('highUsageAlert')}`,
        body: `${t('fiveHourUsage')} ${primaryPercent.toFixed(0)}%`
      });
      lastNotifiedPrimary = true;
    }

    if (shouldNotifySecondary) {
      console.debug("Sending secondary usage notification:", secondaryPercent);
      await sendNotification({
        title: `${providerName}: ${t('highUsageAlert')}`,
        body: `${t('weeklyUsage')} ${secondaryPercent.toFixed(0)}%`
      });
      lastNotifiedSecondary = true;
    }
  } catch (e) {
    console.error("Notification error:", e);
    // Show in-app toast as fallback
    if (shouldNotifyPrimary || shouldNotifySecondary) {
      showToast(t('highUsageAlert'), 'error');
    }
  }
}


// Autostart
async function getAutostart(): Promise<boolean> {
  try {
    const enabled = await invoke<boolean>("get_autostart_enabled");
    console.debug("Autostart status:", enabled);
    return enabled;
  } catch (e) {
    console.error("Failed to get autostart status:", e);
    return false;
  }
}

async function setAutostart(enabled: boolean): Promise<void> {
  try {
    await invoke("set_autostart_enabled", { enabled });
    console.debug("Autostart set to:", enabled);
    showToast(t('settingsSaved'), 'success');
  } catch (e) {
    console.error("Autostart error:", e);
    showToast(t('fetchError'), 'error');
    // Revert toggle state on error
    const toggle = document.getElementById('autostartToggle') as HTMLInputElement;
    if (toggle) toggle.checked = !enabled;
  }
}

// Retry wrapper
async function withRetry<T>(fn: () => Promise<T>, retries: number = MAX_RETRIES): Promise<T> {
  let lastError: Error | null = null;
  for (let i = 0; i < retries; i++) {
    try { return await fn(); } catch (e) {
      lastError = e as Error;
      if (i < retries - 1) await delay(RETRY_DELAY_MS * (i + 1));
    }
  }
  throw lastError;
}

async function checkBackend(): Promise<boolean> {
  try { return await invoke<boolean>("check_backend"); } catch { return false; }
}

// Account management
async function fetchAccounts(): Promise<void> {
  try {
    const response = await invoke<{ accounts: Account[] }>("get_accounts", { provider: currentProvider });
    accounts = response.accounts || [];
  } catch (e) {
    console.error("Fetch accounts error:", e);
    accounts = [];
  }
}

async function addAccount(): Promise<void> {
  try {
    const initialCount = accounts.length;
    setButtonLoading("addAccountBtn", true);
    
    if (currentProvider === 'antigravity') {
      await invoke("add_account_antigravity");
    } else {
      await invoke("add_account_openai");
    }

    // Poll for new account with proper check
    let attempts = 0;
    const poll = async () => {
      attempts++;
      await fetchAccounts();

      // Check if new account was added
      if (accounts.length > initialCount) {
        setButtonLoading("addAccountBtn", false);
        await refresh();
        return;
      }

      if (attempts < 30) {
        setTimeout(poll, Math.min(2000 * Math.pow(1.2, attempts - 1), 5000));
      } else {
        setButtonLoading("addAccountBtn", false);
      }
    };
    setTimeout(poll, 3000);
  } catch (e) {
    console.error("Add account error:", e);
    setButtonLoading("addAccountBtn", false);
  }
}

async function switchAccount(accountId: string): Promise<void> {
  try {
    // Immediately update UI
    const nameEl = document.querySelector('#accountSelector .account-name');
    const targetAcc = accounts.find(a => a.id === accountId);
    if (nameEl && targetAcc) nameEl.textContent = targetAcc.name;

    // Mark as active locally for instant feedback
    accounts.forEach(a => a.is_active = a.id === accountId);

    // Then do the actual switch in background
    await invoke("activate_account", { accountId });

    // Refresh data in background (don't await to keep UI responsive)
    refresh();
  } catch (e) { console.error("Switch account error:", e); }
}

async function renameAccount(accountId: string, name: string): Promise<void> {
  // Validate account name
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > 50 || !/^[a-zA-Z0-9\s\-_а-яА-ЯёЁ]+$/.test(trimmed)) {
    showToast(t('fetchError'), 'error');
    return;
  }

  try {
    await invoke("update_account_name", { accountId, name: trimmed });
    await fetchAccounts();
    editingAccountId = null;
    showToast(t('accountRenamed'), 'success');
    renderContent();
  } catch (e) {
    console.error("Rename account error:", e);
    showToast(t('fetchError'), 'error');
  }
}

async function removeAccount(accountId: string): Promise<void> {
  // Prevent deleting active account from UI
  const targetAccount = accounts.find(a => a.id === accountId);
  if (targetAccount?.is_active) {
    showToast(t('fetchError'), 'error');
    return;
  }

  const confirmed = await showConfirmDialog(t('confirmDelete'), t('confirmDeleteDesc'));
  if (!confirmed) return;

  try {
    await invoke("delete_account", { accountId });
    // Update local state immediately for responsive UI
    accounts = accounts.filter(a => a.id !== accountId);
    showToast(t('accountDeleted'), 'success');
    // Refresh in background to sync with backend
    await refresh();
  } catch (e) {
    console.error("Delete account error:", e);
    // Refresh accounts to ensure UI is in sync with backend
    await fetchAccounts();
    showToast(t('fetchError'), 'error');
  }
}


async function refresh(): Promise<void> {
  if (isLoading) return;

  setButtonLoading("refreshBtn", true);
  isLoading = true;

  try {
    backendAvailable = await checkBackend();

    if (!backendAvailable) {
      // Try to use cached data
      const cached = loadFromCache();
      if (cached && cached.limits) {
        limitsData = cached.limits;
        accounts = cached.accounts;
        if (cached.currentProvider) currentProvider = cached.currentProvider;
        renderContent();
        updateLastUpdate(cached.timestamp, isCacheStale(cached.timestamp));
        return;
      }
      showBackendError();
      return;
    }

    await fetchAccounts();
    const response = await withRetry(() => invoke<{ providers: Record<string, LimitsData> }>("fetch_limits"));
    
    // Update limits for all providers
    if (response.providers?.openai) {
      limitsData.openai = response.providers.openai;
    }
    if (response.providers?.antigravity) {
      limitsData.antigravity = response.providers.antigravity;
    }

    // Save to cache
    saveToCache(limitsData, accounts);

    renderContent();
    updateLastUpdate(Date.now(), false);

    const currentLimits = limitsData[currentProvider];
    if (currentLimits?.is_authenticated) await checkAndNotify(currentLimits);
  } catch (e) {
    console.error("Refresh error:", e);
    // Try cached data on error
    const cached = loadFromCache();
    if (cached && cached.limits) {
      limitsData = cached.limits;
      accounts = cached.accounts;
      if (cached.currentProvider) currentProvider = cached.currentProvider;
      renderContent();
      updateLastUpdate(cached.timestamp, isCacheStale(cached.timestamp));
    } else {
      showError(t('fetchError'));
    }
  } finally {
    setButtonLoading("refreshBtn", false);
    isLoading = false;
  }
}

async function login(): Promise<void> {
  setButtonLoading("loginBtn", true, t('openingBrowser'));

  try {
    if (currentProvider === 'antigravity') {
      await invoke("login_antigravity");
    } else {
      await invoke("login_openai");
    }
    
    let attempts = 0;
    const poll = async () => {
      attempts++;
      await refresh();
      const currentLimits = limitsData[currentProvider];
      if (currentLimits?.is_authenticated) {
        setButtonLoading("loginBtn", false);
        return;
      }
      if (attempts < 30) setTimeout(poll, Math.min(2000 * Math.pow(1.2, attempts - 1), 5000));
      else setButtonLoading("loginBtn", false);
    };
    setTimeout(poll, 3000);
  } catch (e) {
    console.error("Login error:", e);
    setButtonLoading("loginBtn", false);
  }
}

async function logout(): Promise<void> {
  try {
    if (currentProvider === 'antigravity') {
      await invoke("logout_antigravity");
    } else {
      await invoke("logout_openai");
    }
    limitsData[currentProvider] = null;
    accounts = [];
    renderContent();
  } catch (e) { console.error("Logout error:", e); }
}

function switchProvider(provider: Provider): void {
  if (provider === currentProvider) return;
  currentProvider = provider;
  // Fetch accounts for new provider
  fetchAccounts().then(() => renderContent());
}

function getUsageClass(percent: number): string {
  if (percent >= 80) return "high";
  if (percent >= 50) return "medium";
  return "low";
}

function formatResetTime(isoString?: string): string | null {
  if (!isoString) return null;
  const diff = new Date(isoString).getTime() - Date.now();
  if (diff <= 0) return t('resetting');
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  if (days > 0) return `${days}${t('days')} ${hours}${t('hours')}`;
  if (hours > 0) return `${hours}${t('hours')} ${minutes}${t('minutes')}`;
  return `${minutes}${t('minutes')}`;
}

function renderProviderTabs(): string {
  const openaiActive = currentProvider === 'openai' ? 'active' : '';
  const antigravityActive = currentProvider === 'antigravity' ? 'active' : '';
  
  // Show indicator if provider is authenticated
  const openaiConnected = limitsData.openai?.is_authenticated ? '<span class="tab-indicator"></span>' : '';
  const antigravityConnected = limitsData.antigravity?.is_authenticated ? '<span class="tab-indicator"></span>' : '';
  
  return `
    <div class="provider-tabs">
      <button class="provider-tab ${openaiActive}" data-provider="openai">
        <span class="tab-icon openai">${icons.openai}</span>
        <span>OpenAI</span>
        ${openaiConnected}
      </button>
      <button class="provider-tab ${antigravityActive}" data-provider="antigravity">
        <span class="tab-icon antigravity">${icons.sparkles}</span>
        <span>Antigravity</span>
        ${antigravityConnected}
      </button>
    </div>
  `;
}


function renderContent(): void {
  const content = document.getElementById("content");
  if (!content) return;

  if (settingsOpen) { renderSettings(content); return; }
  if (!backendAvailable) { content.innerHTML = renderBackendOffline(); return; }
  
  const currentLimits = limitsData[currentProvider];
  if (isLoading && !currentLimits) { content.innerHTML = renderSkeleton(); return; }
  if (!currentLimits || !currentLimits.is_authenticated) { content.innerHTML = renderNotConnected(); return; }

  content.innerHTML = renderConnected(currentLimits);
}

function renderSkeleton(): string {
  return `
    <div class="card">
      <div class="card-header">
        <div class="provider-info">
          <div class="skeleton" style="width: 32px; height: 32px; border-radius: 6px;"></div>
          <div class="skeleton skeleton-text" style="width: 100px;"></div>
        </div>
        <div class="skeleton" style="width: 80px; height: 24px; border-radius: 12px;"></div>
      </div>
      <div class="skeleton" style="width: 100%; height: 56px; border-radius: 10px; margin-bottom: 16px;"></div>
      <div class="skeleton" style="width: 100%; height: 48px; border-radius: 10px; margin-bottom: 20px;"></div>
      <div style="margin-bottom: 20px;">
        <div class="skeleton skeleton-text" style="width: 120px; margin-bottom: 12px;"></div>
        <div class="skeleton skeleton-bar" style="width: 100%;"></div>
      </div>
      <div class="skeleton" style="width: 100%; height: 1px; margin: 20px 0;"></div>
      <div>
        <div class="skeleton skeleton-text" style="width: 100px; margin-bottom: 12px;"></div>
        <div class="skeleton skeleton-bar" style="width: 100%;"></div>
      </div>
    </div>
  `;
}

async function renderSettings(content: HTMLElement): Promise<void> {
  const autostartEnabled = await getAutostart();
  const currentLocale = getLocale();
  const locales = getAvailableLocales();

  content.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="provider-info">
          <div class="provider-icon" style="background: linear-gradient(135deg, var(--accent-violet), var(--accent-indigo));">${icons.settings}</div>
          <span class="provider-name">${t('settingsTitle').toUpperCase()}</span>
        </div>
        <button class="btn-icon" id="closeSettingsBtn" title="Close">${icons.x}</button>
      </div>
      <div class="settings-section">
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">${icons.rocket} ${t('startWithWindows')}</span>
            <span class="setting-desc">${t('startWithWindowsDesc')}</span>
          </div>
          <label class="toggle"><input type="checkbox" id="autostartToggle" ${autostartEnabled ? 'checked' : ''}><span class="toggle-slider"></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">${icons.bell} ${t('usageAlerts')}</span>
            <span class="setting-desc">${t('usageAlertsDesc')} ${NOTIFICATION_THRESHOLD}%</span>
          </div>
          <label class="toggle"><input type="checkbox" id="notificationsToggle" ${notificationsEnabled ? 'checked' : ''}><span class="toggle-slider"></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">${icons.refresh} ${t('autoRefresh')}</span>
            <span class="setting-desc">${t('autoRefreshDesc')}</span>
          </div>
          <label class="toggle"><input type="checkbox" id="autoRefreshToggle" ${autoRefreshEnabled ? 'checked' : ''}><span class="toggle-slider"></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">${icons.globe} ${t('language')}</span>
            <span class="setting-desc">${t('languageDesc')}</span>
          </div>
          <select id="localeSelect" class="locale-select">
            ${locales.map(l => `<option value="${l.code}" ${l.code === currentLocale ? 'selected' : ''}>${l.name}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="settings-footer"><span class="version">v${appVersion}</span></div>
    </div>
  `;
}

function renderBackendOffline(): string {
  return `
    <div class="card">
      <div class="card-header">
        <div class="provider-info">
          <div class="provider-icon" style="background: linear-gradient(135deg, #ef4444, #dc2626);">${icons.alert}</div>
          <span class="provider-name">${t('backendOffline').toUpperCase()}</span>
        </div>
        <span class="status offline">${t('offline')}</span>
      </div>
      <div class="empty-state">
        <div class="icon">${icons.plug}</div>
        <p>${t('backendNotRunning')} ${t('startBackendFirst')}</p>
        <code>cd backend && python -m uvicorn app.main:app --port 1455</code>
      </div>
      <button class="btn-connect" id="retryBtn">${t('checkAgain')}</button>
    </div>
  `;
}

function renderNotConnected(): string {
  const isAntigravity = currentProvider === 'antigravity';
  const providerName = isAntigravity ? 'ANTIGRAVITY' : 'OPENAI CODEX';
  const providerIcon = isAntigravity ? icons.sparkles : icons.openai;
  const providerIconClass = isAntigravity ? 'antigravity' : 'openai';
  
  return `
    ${renderProviderTabs()}
    <div class="card">
      <div class="card-header">
        <div class="provider-info">
          <div class="provider-icon ${providerIconClass}">${providerIcon}</div>
          <span class="provider-name">${providerName}</span>
        </div>
        <span class="status offline">${t('offline')}</span>
      </div>
      <div class="empty-state">
        <div class="icon">${icons.lock}</div>
        <p>${t('connectToTrack')}</p>
      </div>
      <button class="btn-connect" id="loginBtn">${t('connectAccount')}</button>
    </div>
  `;
}


function renderConnected(data: LimitsData): string {
  const isAntigravity = currentProvider === 'antigravity';
  const providerName = isAntigravity ? 'ANTIGRAVITY' : 'OPENAI CODEX';
  const providerIcon = isAntigravity ? icons.sparkles : icons.openai;
  const providerIconClass = isAntigravity ? 'antigravity' : 'openai';
  
  const activeAccount = accounts.find(a => a.is_active);
  const accountName = activeAccount?.name || t('account');
  const safeAccountName = escapeHtml(accountName);
  const cardClass = isFirstRender ? 'card animated' : 'card';
  isFirstRender = false;

  let html = `
    ${renderProviderTabs()}
    <div class="${cardClass}">
      <div class="card-header">
        <div class="provider-info">
          <div class="provider-icon ${providerIconClass}">${providerIcon}</div>
          <span class="provider-name">${providerName}</span>
        </div>
        <span class="status online">${t('connected')}</span>
      </div>
  `;

  // Account selector
  html += `
    <div class="account-selector">
      <div class="account-row editable" id="accountSelector">
        <div class="account-icon">${icons.user}</div>
        <div class="account-info">
          <span class="account-label">${t('account')}</span>
          <span class="account-name">${safeAccountName}</span>
        </div>
        <span class="account-edit-hint">${icons.chevronDown}</span>
      </div>
    </div>
  `;

  if (isAntigravity) {
    // Antigravity: show models list
    html += renderAntigravityModels(data);
  } else {
    // OpenAI: show primary/secondary usage
    html += renderOpenAIUsage(data);
  }

  if (data.error) html += `<div class="error-msg"><span>${icons.alert}</span><span>${escapeHtml(data.error)}</span></div>`;

  html += `</div>`;
  return html;
}

function renderOpenAIUsage(data: LimitsData): string {
  const primaryPercent = data.primary_used_percent ?? 0;
  const secondaryPercent = data.secondary_used_percent ?? 0;
  const primaryClass = getUsageClass(primaryPercent);
  const secondaryClass = getUsageClass(secondaryPercent);
  const planIcon = data.plan_type?.toLowerCase() === 'team' ? icons.users :
    data.plan_type?.toLowerCase() === 'pro' ? icons.star : icons.crown;

  let html = '';

  if (data.plan_type) {
    html += `
      <div class="plan-row">
        <span class="plan-icon">${planIcon}</span>
        <div class="plan-info">
          <span class="plan-label">${t('currentPlan')}</span>
          <span class="plan-value">${escapeHtml(data.plan_type)}</span>
        </div>
      </div>
    `;
  }

  // Primary usage
  html += `
    <div class="usage-block">
      <div class="usage-header">
        <span class="usage-label"><span class="usage-label-icon">${icons.bolt}</span>${t('fiveHourWindow')}</span>
        <span class="usage-percent ${primaryClass}">${primaryPercent.toFixed(0)}%</span>
      </div>
      <div class="progress-track"><div class="progress-bar ${primaryClass}" style="width: ${Math.min(primaryPercent, 100)}%"></div></div>
  `;
  const primaryReset = formatResetTime(data.primary_reset_at);
  if (primaryReset) html += `<div class="reset-time"><span class="reset-time-icon">${icons.clock}</span>${t('resetsIn')} <span class="reset-time-value">${primaryReset}</span></div>`;
  html += `</div><div class="divider"></div>`;

  // Secondary usage
  html += `
    <div class="usage-block">
      <div class="usage-header">
        <span class="usage-label"><span class="usage-label-icon">${icons.calendar}</span>${t('weeklyWindow')}</span>
        <span class="usage-percent ${secondaryClass}">${secondaryPercent.toFixed(0)}%</span>
      </div>
      <div class="progress-track"><div class="progress-bar ${secondaryClass}" style="width: ${Math.min(secondaryPercent, 100)}%"></div></div>
  `;
  const secondaryReset = formatResetTime(data.secondary_reset_at);
  if (secondaryReset) html += `<div class="reset-time"><span class="reset-time-icon">${icons.clock}</span>${t('resetsIn')} <span class="reset-time-value">${secondaryReset}</span></div>`;
  html += `</div>`;

  return html;
}

// Model sort order (lower = higher priority)
const MODEL_SORT_ORDER: Record<string, number> = {
  // Gemini models first
  'gemini-3-flash': 1,
  'gemini-3-pro-low': 2,
  'gemini-2.5-pro': 3,
  'gemini-2.5-flash': 4,
  'gemini-3-pro-image': 5,
  'gemini-3-pro-high': 6,
  // Claude models after
  'claude-sonnet-4': 10,
  'claude-sonnet-4-thinking': 11,
  'claude-4.5': 12,
  'claude-sonnet-4-5': 12,
  'claude-sonnet-4-5-thinking': 13,
  'claude-3-7-sonnet': 14,
  'claude-3-7-sonnet-thinking': 15,
};

function getModelSortKey(modelName: string): number {
  const lowerName = modelName.toLowerCase();
  // Check exact match
  if (MODEL_SORT_ORDER[lowerName] !== undefined) {
    return MODEL_SORT_ORDER[lowerName];
  }
  // Check partial match
  for (const [key, order] of Object.entries(MODEL_SORT_ORDER)) {
    if (lowerName.includes(key)) return order;
  }
  // Unknown models at the end
  return lowerName.includes('gemini') ? 9 : 20;
}

// Format model name nicely if backend didn't provide display_name
function formatModelDisplayName(name: string): string {
  // If already looks formatted (has spaces and capitals), return as is
  if (name.includes(' ') && /[A-Z]/.test(name)) {
    return name;
  }
  
  // Handle special patterns
  let formatted = name
    // Replace dashes/underscores with spaces
    .replace(/[-_]/g, ' ')
    // Handle version numbers like "4-5" -> "4.5", "3-7" -> "3.7"
    .replace(/(\d) (\d)/g, '$1.$2')
    // Capitalize first letter of each word
    .split(' ')
    .map(word => {
      // Keep version numbers as is
      if (/^\d/.test(word)) return word;
      // Capitalize word
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(' ');
  
  // Fix common patterns
  formatted = formatted
    .replace(/^Gemini (\d)/i, 'Gemini $1')
    .replace(/^Claude /i, 'Claude ')
    .replace(/ Pro /i, ' Pro ')
    .replace(/ Flash/i, ' Flash')
    .replace(/ Sonnet/i, ' Sonnet')
    .replace(/ Image/i, ' Image')
    .replace(/ High\)?$/i, ' (High)')
    .replace(/ Low\)?$/i, ' (Low)')
    .replace(/ Thinking\)?$/i, ' (Thinking)')
    .replace(/\( /g, '(')
    .replace(/ \)/g, ')');
  
  return formatted;
}

function renderAntigravityModels(data: LimitsData): string {
  const models = data.models || [];
  
  if (models.length === 0) {
    return `<div class="empty-state" style="padding: 20px 0;"><p>No models available</p></div>`;
  }

  // Sort models by predefined order
  const sortedModels = [...models].sort((a, b) => {
    return getModelSortKey(a.model_name) - getModelSortKey(b.model_name);
  });

  let html = `<div class="models-list">`;
  
  for (const model of sortedModels) {
    const usageClass = getUsageClass(model.used_percent);
    const resetTime = formatResetTime(model.reset_time);
    
    // Determine model icon based on name
    const modelNameLower = model.model_name.toLowerCase();
    const isGemini = modelNameLower.includes('gemini');
    const isClaude = modelNameLower.includes('claude');
    const modelIcon = isGemini ? icons.gemini : (isClaude ? icons.claude : icons.sparkles);
    const modelIconClass = isGemini ? 'gemini' : (isClaude ? 'claude' : '');
    
    // Format display name nicely
    const displayName = formatModelDisplayName(model.display_name || model.model_name);
    
    html += `
      <div class="model-item">
        <div class="model-header">
          <div class="model-info">
            <span class="model-icon ${modelIconClass}">${modelIcon}</span>
            <span class="model-name">${escapeHtml(displayName)}</span>
          </div>
          <span class="usage-percent ${usageClass}">${model.used_percent.toFixed(0)}%</span>
        </div>
        <div class="progress-track small"><div class="progress-bar ${usageClass}" style="width: ${Math.min(model.used_percent, 100)}%"></div></div>
        ${resetTime ? `<div class="reset-time small"><span class="reset-time-icon">${icons.clock}</span>${t('resetsIn')} <span class="reset-time-value">${resetTime}</span></div>` : ''}
      </div>
    `;
  }
  
  html += `</div>`;
  return html;
}


function renderAccountsDropdown(): string {
  return `<div class="account-dropdown">${renderAccountsDropdownContent()}</div>`;
}

function renderAccountsDropdownContent(): string {
  let html = '';

  for (const acc of accounts) {
    const safeName = escapeHtml(acc.name);
    const safeNameAttr = escapeAttr(acc.name);
    const safeId = escapeAttr(acc.id);
    if (editingAccountId === acc.id) {

      html += `
        <div class="account-item ${acc.is_active ? 'active' : ''}">
          <div class="account-item-icon">${icons.user}</div>
          <input type="text" class="account-name-input" id="editNameInput" value="${safeNameAttr}" maxlength="30" autofocus>
          <div class="account-edit-actions">
            <button class="btn-save" data-save-id="${safeId}">${icons.check}</button>

            <button class="btn-cancel" id="cancelEditBtn">${icons.x}</button>
          </div>
        </div>
      `;
    } else {
      html += `
        <div class="account-item ${acc.is_active ? 'active' : ''}" data-account-id="${safeId}">
          <div class="account-item-icon">${icons.user}</div>
          <div class="account-item-info">
            <span class="account-item-name">${safeName}</span>
            <span class="account-item-status ${acc.is_active ? 'active' : ''}">${acc.is_active ? t('active') : ''}</span>
          </div>
          <div class="account-item-actions">
            <button class="btn-account-action" data-edit-id="${safeId}" title="${t('rename')}">${icons.pencil}</button>
            ${!acc.is_active ? `<button class="btn-account-action delete" data-delete-id="${safeId}" title="${t('delete')}">${icons.trash}</button>` : ''}
          </div>
        </div>

      `;
    }
  }

  html += `
    <div class="dropdown-divider"></div>
    <div class="dropdown-item" id="addAccountBtn">
      <span style="color: var(--accent-violet)">${icons.plus}</span>
      <span>${t('addAccount')}</span>
    </div>
  `;

  return html;
}

function showBackendError(): void {
  backendAvailable = false;
  renderContent();
}

function showError(msg: string): void {
  const content = document.getElementById("content");
  if (!content) return;
  const safeMsg = escapeHtml(msg);
  content.innerHTML = `
    <div class="card">
      <div class="error-msg"><span>${icons.alert}</span><span>${safeMsg}</span></div>
      <button class="btn-connect" id="retryBtn" style="margin-top: 16px;">${t('tryAgain')}</button>
    </div>
  `;
}


function updateLastUpdate(timestamp: number = Date.now(), isStale: boolean = false): void {
  const el = document.getElementById("lastUpdate");
  if (el) {
    const time = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (isStale) {
      el.innerHTML = `<span class="stale-indicator">⚠️</span> ${t('cached')} ${time}`;
      el.style.color = 'var(--warning)';
      el.title = t('fetchError');
    } else {
      el.textContent = `${t('updated')} ${time}`;
      el.style.color = '';
      el.title = '';
    }
  }
}


// Event handlers
document.addEventListener("click", async (e) => {
  const target = e.target as HTMLElement;
  const btn = target.closest('button');

  // Provider tab click
  const providerTab = target.closest('.provider-tab') as HTMLElement;
  if (providerTab && providerTab.dataset.provider) {
    const provider = providerTab.dataset.provider as Provider;
    switchProvider(provider);
    return;
  }

  // Account selector toggle
  if (target.closest('#accountSelector')) {
    accountsExpanded = !accountsExpanded;
    const selector = document.querySelector('.account-selector');

    // Remove all existing dropdowns first to prevent duplicates
    document.querySelectorAll('.account-dropdown').forEach(d => d.remove());

    if (accountsExpanded && selector) {
      selector.insertAdjacentHTML('beforeend', renderAccountsDropdown());
    }
    return;
  }

  // Click outside dropdown closes it
  if (accountsExpanded && !target.closest('.account-dropdown') && !target.closest('#accountSelector')) {
    accountsExpanded = false;
    document.querySelector('.account-dropdown')?.remove();
    return;
  }

  // Account item click (switch account)
  const accountItem = target.closest('.account-item[data-account-id]') as HTMLElement;
  if (accountItem && !target.closest('.account-item-actions')) {
    const accountId = accountItem.dataset.accountId;
    if (accountId) {
      // Close dropdown immediately
      accountsExpanded = false;
      document.querySelector('.account-dropdown')?.remove();
      // Switch account
      switchAccount(accountId);
    }
    return;
  }

  // Edit account name
  const editBtn = target.closest('[data-edit-id]') as HTMLElement;
  if (editBtn) {
    editingAccountId = editBtn.dataset.editId || null;
    const dropdown = document.querySelector('.account-dropdown');
    if (dropdown) {
      dropdown.innerHTML = renderAccountsDropdownContent();
      setTimeout(() => document.getElementById('editNameInput')?.focus(), 0);
    }
    return;
  }

  // Save account name
  const saveBtn = target.closest('[data-save-id]') as HTMLElement;
  if (saveBtn) {
    const input = document.getElementById('editNameInput') as HTMLInputElement;
    if (input && saveBtn.dataset.saveId) {
      await renameAccount(saveBtn.dataset.saveId, input.value);
      const dropdown = document.querySelector('.account-dropdown');
      if (dropdown) dropdown.innerHTML = renderAccountsDropdownContent();
      // Update account name in selector
      const nameEl = document.querySelector('#accountSelector .account-name');
      const activeAcc = accounts.find(a => a.is_active);
      if (nameEl && activeAcc) nameEl.textContent = activeAcc.name;
    }
    return;
  }

  // Cancel edit
  if (btn?.id === 'cancelEditBtn') {
    editingAccountId = null;
    const dropdown = document.querySelector('.account-dropdown');
    if (dropdown) dropdown.innerHTML = renderAccountsDropdownContent();
    return;
  }

  // Delete account
  const deleteBtn = target.closest('[data-delete-id]') as HTMLElement;
  if (deleteBtn && deleteBtn.dataset.deleteId) {
    await removeAccount(deleteBtn.dataset.deleteId);
    const dropdown = document.querySelector('.account-dropdown');
    if (dropdown) dropdown.innerHTML = renderAccountsDropdownContent();
    return;
  }

  // Add account
  if (target.closest('#addAccountBtn')) {
    accountsExpanded = false;
    document.querySelector('.account-dropdown')?.remove();
    await addAccount();
    return;
  }

  // Other buttons
  if (!btn) return;
  if (btn.id === "loginBtn" && !btn.hasAttribute("disabled")) login();
  if (btn.id === "logoutBtn") logout();
  if (btn.id === "retryBtn") debouncedRefresh();
  if (btn.id === "refreshBtn") debouncedRefresh();
  if (btn.id === "settingsBtn") { settingsOpen = true; renderContent(); }
  if (btn.id === "closeSettingsBtn") { settingsOpen = false; renderContent(); }
});

document.addEventListener("change", async (e) => {
  const target = e.target as HTMLInputElement | HTMLSelectElement;
  if (target.id === "autostartToggle") await setAutostart((target as HTMLInputElement).checked);
  if (target.id === "notificationsToggle") { notificationsEnabled = (target as HTMLInputElement).checked; saveSettings(); }
  if (target.id === "autoRefreshToggle") { autoRefreshEnabled = (target as HTMLInputElement).checked; saveSettings(); startAutoRefresh(); }
  if (target.id === "localeSelect") { setLocale(target.value as Locale); renderContent(); }
});

document.addEventListener("keydown", (e) => {
  if (editingAccountId) {
    if (e.key === "Enter") {
      e.preventDefault();
      const input = document.getElementById('editNameInput') as HTMLInputElement;
      if (input) renameAccount(editingAccountId, input.value);
    }
    if (e.key === "Escape") {
      e.preventDefault();
      editingAccountId = null;
      renderContent();
    }
  }
});

// Debounced refresh to prevent rapid calls
const debouncedRefresh = debounce(refresh, 300);

// Initialize
let refreshInterval: number | null = null;
let isWindowVisible = true;

function startAutoRefresh(): void {
  if (refreshInterval) {
    clearInterval(refreshInterval);
    refreshInterval = null;
  }

  if (autoRefreshEnabled && isWindowVisible) {
    refreshInterval = setInterval(() => {
      if (isWindowVisible && autoRefreshEnabled) {
        void refresh();
      }
    }, 5 * 60 * 1000) as unknown as number;
  }
}

function stopAutoRefresh(): void {
  if (refreshInterval) {
    clearInterval(refreshInterval);
    refreshInterval = null;
  }
}

// Handle window visibility changes
document.addEventListener("visibilitychange", () => {
  isWindowVisible = document.visibilityState === "visible";

  if (isWindowVisible) {
    // Window became visible - restart auto-refresh (no immediate refresh)
    startAutoRefresh();
  } else {
    // Window hidden - stop auto-refresh to save resources
    stopAutoRefresh();
  }
});

// Global error handlers
window.addEventListener('error', (event) => {
  console.error('Uncaught error:', event.error);
  showError(t('fetchError'));
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled rejection:', event.reason);
  event.preventDefault();
});

document.addEventListener("DOMContentLoaded", () => {
  loadSettings();
  refresh();
  startAutoRefresh();
});
