import type { VellumApiConfig, VellumTheme } from '../lib/vellum-core';

const t = (fontSize: string, fontWeight: number, lineHeight: string) => ({
  fontSize,
  fontWeight,
  lineHeight,
});

export const apiConfig: VellumApiConfig = {
  baseUrl: '',
  getAccessToken: async () => 'demo-token',
  endpoints: {
    negotiation: '/api/negotiation',
    agent: '/api/agent',
  },
};

export const theme: VellumTheme = {
  colors: {
    primary: '#6366f1',
    primaryDark: '#4f46e5',
    primaryLight: '#818cf8',
    textPrimary: '#f8fafc',
    textSecondary: '#94a3b8',
    textMuted: '#64748b',
    background: '#0f172a',
    backgroundPaper: '#1e293b',
    backgroundSubtle: '#1a2332',
    surfaceRaised: '#334155',
    divider: '#334155',
    borderLight: '#475569',
    inputBackground: '#1e293b',
    success: '#22c55e',
    successBg: '#052e16',
    successText: '#4ade80',
    error: '#ef4444',
    errorBg: '#450a0a',
    errorText: '#f87171',
    warning: '#f59e0b',
    warningBg: '#451a03',
    warningText: '#fbbf24',
  },
  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    headingFontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    scale: {
      h1: t('2rem', 700, '1.2'),
      h2: t('1.5rem', 700, '1.3'),
      h3: t('1.25rem', 600, '1.4'),
      h4: t('1.125rem', 600, '1.4'),
      h5: t('1rem', 600, '1.5'),
      h6: t('0.875rem', 600, '1.5'),
      body1: t('0.9375rem', 400, '1.6'),
      body2: t('0.8125rem', 400, '1.6'),
      caption: t('0.75rem', 400, '1.5'),
    },
  },
  spacing: { xs: '4px', sm: '8px', md: '16px', lg: '24px', xl: '32px', xxl: '48px' },
  borderRadius: { none: '0', sm: '4px', md: '8px', lg: '12px', xl: '16px', full: '9999px' },
  shadows: {
    none: 'none',
    subtle: '0 1px 2px rgba(0,0,0,0.3)',
    card: '0 4px 12px rgba(0,0,0,0.4)',
    elevated: '0 8px 24px rgba(0,0,0,0.5)',
  },
  zIndex: { base: 0, raised: 1, dropdown: 100, sticky: 200, modal: 300, toast: 400 },
};
