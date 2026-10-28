export type Theme = 'system' | 'light' | 'dark';
export const THEME_KEY = 'clonarch-theme';

export function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* Storage can be unavailable in private/restricted browsers. */ }
  return 'system';
}

export function applyTheme(theme: Theme, systemDark: boolean): void {
  const dark = theme === 'dark' || (theme === 'system' && systemDark);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#18181b' : '#f5f7f4');
}

export function saveTheme(theme: Theme): void {
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* Still apply for this page. */ }
}
