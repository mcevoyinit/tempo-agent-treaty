/**
 * Local Vellum Core — thin provider without Emotion dependency.
 *
 * The full @vellum/ui uses Emotion's ThemeProvider which creates
 * build complexity with the JSX runtime. For the hackathon demo,
 * we provide the same context API without Emotion.
 */

import { createContext, useContext, type ReactNode } from 'react';

export interface TypographySpec {
  fontSize: string;
  fontWeight: number;
  lineHeight: string;
}

export interface VellumTheme {
  colors: Record<string, string>;
  typography: {
    fontFamily: string;
    headingFontFamily: string;
    scale: Record<string, TypographySpec>;
  };
  spacing: Record<string, string>;
  borderRadius: Record<string, string>;
  shadows: Record<string, string>;
  zIndex: Record<string, number>;
}

export interface VellumApiConfig {
  baseUrl: string;
  getAccessToken: () => Promise<string>;
  endpoints?: Record<string, string>;
}

interface VellumContextValue {
  theme: VellumTheme;
  apiConfig: VellumApiConfig;
}

const VellumContext = createContext<VellumContextValue | null>(null);

export function VellumProvider({
  theme,
  apiConfig,
  children,
}: {
  theme: VellumTheme;
  apiConfig: VellumApiConfig;
  children: ReactNode;
}) {
  return (
    <VellumContext.Provider value={{ theme, apiConfig }}>
      {children}
    </VellumContext.Provider>
  );
}

export function useVellum(): VellumContextValue {
  const ctx = useContext(VellumContext);
  if (!ctx) throw new Error('useVellum must be used within <VellumProvider>');
  return ctx;
}

export function useVellumApi() {
  return useVellum().apiConfig;
}

export function useVellumTheme() {
  return useVellum().theme;
}
