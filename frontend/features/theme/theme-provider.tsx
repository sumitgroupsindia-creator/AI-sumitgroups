'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Moon, Sun } from 'lucide-react';

import { cn } from '@/lib/utils';

export type Theme = 'dark' | 'light';

export const THEME_STORAGE_KEY = 'sg-theme';

/**
 * Runs before the first paint, from a blocking <script> in the document head.
 *
 * Without it the page paints in the default theme and then corrects itself once React hydrates,
 * which on a dark-first design is a full-screen white flash on every navigation. Kept as a string
 * because it has to execute ahead of the bundle, and deliberately wrapped in try/catch: a browser
 * with site data blocked throws on `localStorage` access, and a themed page is worth less than a
 * page that renders at all.
 */
export const THEME_BOOT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('${THEME_STORAGE_KEY}');
    var theme = stored === 'light' || stored === 'dark' ? stored : 'dark';
    document.documentElement.classList.toggle('dark', theme === 'dark');
  } catch (e) {
    document.documentElement.classList.add('dark');
  }
})();
`;

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  setTheme: () => {},
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Seeded to the default rather than read from the DOM, so server and client render the same
  // thing. The effect below reconciles with whatever the boot script already applied.
  const [theme, setThemeState] = useState<Theme>('dark');

  useEffect(() => {
    setThemeState(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    document.documentElement.classList.toggle('dark', next === 'dark');
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* a browser with site data blocked still gets the theme, just not the memory of it */
    }
  }, []);

  const toggle = useCallback(
    () => setTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark'),
    [setTheme],
  );

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const nextIsDark = theme === 'light';

  return (
    <button
      type="button"
      onClick={toggle}
      title={nextIsDark ? 'डार्क मोड' : 'लाइट मोड'}
      className={cn(
        'inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
        className,
      )}
    >
      {nextIsDark ? <Moon className="h-[18px] w-[18px]" /> : <Sun className="h-[18px] w-[18px]" />}
      <span className="sr-only">{nextIsDark ? 'डार्क मोड' : 'लाइट मोड'}</span>
    </button>
  );
}
