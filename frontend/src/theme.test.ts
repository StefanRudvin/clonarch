// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, readTheme, saveTheme, THEME_KEY } from './theme';

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.head.innerHTML = '<meta name="theme-color" content="#f5f7f4">';
});

describe('appearance preferences', () => {
  it('defaults to system and ignores invalid stored preferences', () => {
    expect(readTheme()).toBe('system');
    localStorage.setItem(THEME_KEY, 'invalid');
    expect(readTheme()).toBe('system');
  });

  it.each(['light', 'dark', 'system'] as const)('persists %s across reads', theme => {
    saveTheme(theme);
    expect(readTheme()).toBe(theme);
  });

  it.each([
    ['system', true, 'dark'], ['system', false, 'light'],
    ['light', true, 'light'], ['dark', false, 'dark'],
  ] as const)('resolves %s with system dark=%s to %s', (theme, systemDark, expected) => {
    applyTheme(theme, systemDark);
    expect(document.documentElement.dataset.theme).toBe(expected);
    expect(document.querySelector('meta')?.getAttribute('content')).toBe(expected === 'dark' ? '#18181b' : '#f5f7f4');
  });

  it('continues to apply appearance when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readTheme()).toBe('system');
    expect(() => saveTheme('dark')).not.toThrow();
    applyTheme('dark', false);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('updates system appearance when the device preference changes', () => {
    applyTheme('system', false);
    applyTheme('system', true);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
