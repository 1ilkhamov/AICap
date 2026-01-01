/**
 * Internationalization (i18n) support for AICap
 */

export type Locale = 'en' | 'ru';

interface Translations {
  // Header
  appName: string;
  refresh: string;
  settings: string;
  
  // Status
  connected: string;
  offline: string;
  
  // Provider
  openaiCodex: string;
  backendOffline: string;
  
  // Usage
  fiveHourWindow: string;
  weeklyWindow: string;
  resetsIn: string;
  resetting: string;
  
  // Plan
  currentPlan: string;
  
  // Account
  account: string;
  clickToSetName: string;
  clickToEdit: string;
  enterName: string;
  save: string;
  cancel: string;
  addAccount: string;
  active: string;
  rename: string;
  delete: string;
  
  // Auth
  connectAccount: string;
  disconnectAccount: string;
  openingBrowser: string;
  
  // Backend offline
  backendNotRunning: string;
  startBackendFirst: string;
  checkAgain: string;
  
  // Not connected
  connectToTrack: string;
  
  // Settings
  settingsTitle: string;
  startWithWindows: string;
  startWithWindowsDesc: string;
  usageAlerts: string;
  usageAlertsDesc: string;
  autoRefresh: string;
  autoRefreshDesc: string;
  enabled: string;
  language: string;
  languageDesc: string;
  
  // Notifications
  highUsageAlert: string;
  fiveHourUsage: string;
  weeklyUsage: string;
  
  // Footer
  updated: string;
  cached: string;
  connecting: string;
  
  // Errors
  fetchError: string;
  tryAgain: string;
  
  // Time
  days: string;
  hours: string;
  minutes: string;
  
  // Toast & Dialogs
  confirmDelete: string;
  confirmDeleteDesc: string;
  confirm: string;
  accountDeleted: string;
  accountRenamed: string;
  accountAdded: string;
  settingsSaved: string;
  loading: string;
  
  // Usage labels
  remaining: string;
  used: string;
}

const translations: Record<Locale, Translations> = {
  en: {
    appName: 'AICap',
    refresh: 'Refresh',
    settings: 'Settings',
    connected: 'Connected',
    offline: 'Offline',
    openaiCodex: 'OpenAI Codex',
    backendOffline: 'Backend Offline',
    fiveHourWindow: '5-Hour Window',
    weeklyWindow: 'Weekly Window',
    resetsIn: 'Resets in',
    resetting: 'Resetting...',
    currentPlan: 'Current Plan',
    account: 'Account',
    clickToSetName: 'Click to set name',
    clickToEdit: 'Click to edit',
    enterName: 'Enter name',
    save: 'Save',
    cancel: 'Cancel',
    addAccount: 'Add Account',
    active: 'Active',
    rename: 'Rename',
    delete: 'Delete',
    connectAccount: 'Connect OpenAI Account',
    disconnectAccount: 'Disconnect Account',
    openingBrowser: 'Opening browser...',
    backendNotRunning: 'The backend server is not running.',
    startBackendFirst: 'Please start it first.',
    checkAgain: 'Check Again',
    connectToTrack: 'Connect your OpenAI account to start tracking your usage limits',
    settingsTitle: 'Settings',
    startWithWindows: 'Start with Windows',
    startWithWindowsDesc: 'Launch app automatically on startup',
    usageAlerts: 'Usage Alerts',
    usageAlertsDesc: 'Notify when usage reaches',
    autoRefresh: 'Auto Refresh',
    autoRefreshDesc: 'Update limits every 5 minutes',
    enabled: 'Enabled',
    language: 'Language',
    languageDesc: 'Interface language',
    highUsageAlert: '⚠️ High Usage Alert',
    fiveHourUsage: '5-hour window at',
    weeklyUsage: 'Weekly window at',
    updated: 'Updated',
    cached: 'Cached',
    connecting: 'Connecting...',
    fetchError: 'Failed to fetch limits. Please try again.',
    tryAgain: 'Try Again',
    days: 'd',
    hours: 'h',
    minutes: 'm',
    confirmDelete: 'Delete Account?',
    confirmDeleteDesc: 'This action cannot be undone.',
    confirm: 'Delete',
    accountDeleted: 'Account deleted',
    accountRenamed: 'Account renamed',
    accountAdded: 'Account added',
    settingsSaved: 'Settings saved',
    loading: 'Loading...',
    remaining: 'remaining',
    used: 'used',
  },
  ru: {
    appName: 'AICap',
    refresh: 'Обновить',
    settings: 'Настройки',
    connected: 'Подключено',
    offline: 'Офлайн',
    openaiCodex: 'OpenAI Codex',
    backendOffline: 'Сервер недоступен',
    fiveHourWindow: '5-часовое окно',
    weeklyWindow: 'Недельное окно',
    resetsIn: 'Сброс через',
    resetting: 'Сброс...',
    currentPlan: 'Текущий план',
    account: 'Аккаунт',
    clickToSetName: 'Нажмите для ввода',
    clickToEdit: 'Нажмите для изменения',
    enterName: 'Введите имя',
    save: 'Сохранить',
    cancel: 'Отмена',
    addAccount: 'Добавить аккаунт',
    active: 'Активный',
    rename: 'Переименовать',
    delete: 'Удалить',
    connectAccount: 'Подключить OpenAI',
    disconnectAccount: 'Отключить аккаунт',
    openingBrowser: 'Открываю браузер...',
    backendNotRunning: 'Сервер не запущен.',
    startBackendFirst: 'Сначала запустите его.',
    checkAgain: 'Проверить снова',
    connectToTrack: 'Подключите аккаунт OpenAI для отслеживания лимитов',
    settingsTitle: 'Настройки',
    startWithWindows: 'Запуск с Windows',
    startWithWindowsDesc: 'Автозапуск при старте системы',
    usageAlerts: 'Уведомления',
    usageAlertsDesc: 'Уведомлять при достижении',
    autoRefresh: 'Автообновление',
    autoRefreshDesc: 'Обновлять каждые 5 минут',
    enabled: 'Включено',
    language: 'Язык',
    languageDesc: 'Язык интерфейса',
    highUsageAlert: '⚠️ Высокое использование',
    fiveHourUsage: '5-часовое окно:',
    weeklyUsage: 'Недельное окно:',
    updated: 'Обновлено',
    cached: 'Кэш',
    connecting: 'Подключение...',
    fetchError: 'Не удалось получить лимиты. Попробуйте снова.',
    tryAgain: 'Повторить',
    days: 'д',
    hours: 'ч',
    minutes: 'м',
    confirmDelete: 'Удалить аккаунт?',
    confirmDeleteDesc: 'Это действие нельзя отменить.',
    confirm: 'Удалить',
    accountDeleted: 'Аккаунт удалён',
    accountRenamed: 'Аккаунт переименован',
    accountAdded: 'Аккаунт добавлен',
    settingsSaved: 'Настройки сохранены',
    loading: 'Загрузка...',
    remaining: 'осталось',
    used: 'использовано',
  },
};

const LOCALE_KEY = 'aicap-locale';

export function getLocale(): Locale {
  const saved = localStorage.getItem(LOCALE_KEY);
  if (saved === 'en' || saved === 'ru') return saved;
  
  // Auto-detect from browser
  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith('ru')) return 'ru';
  return 'en';
}

export function setLocale(locale: Locale): void {
  localStorage.setItem(LOCALE_KEY, locale);
}

export function t(key: keyof Translations): string {
  const locale = getLocale();
  return translations[locale][key] || translations.en[key] || key;
}

export function getAvailableLocales(): { code: Locale; name: string }[] {
  return [
    { code: 'en', name: 'English' },
    { code: 'ru', name: 'Русский' },
  ];
}
