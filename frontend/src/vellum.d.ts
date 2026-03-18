/**
 * Type declarations for @vellum/ui — resolved via path alias to source.
 * We declare the modules here to avoid typechecking the full Vellum SDK
 * source (it has its own build process).
 */

declare module '@vellum/ui/core' {
  import { ReactNode } from 'react';

  export interface TypographySpec {
    fontSize: string;
    fontWeight: number;
    lineHeight: string;
  }

  export interface VellumTheme {
    colors: {
      primary: string;
      primaryDark: string;
      primaryLight: string;
      textPrimary: string;
      textSecondary: string;
      textMuted: string;
      background: string;
      backgroundPaper: string;
      backgroundSubtle: string;
      surfaceRaised: string;
      divider: string;
      borderLight: string;
      inputBackground: string;
      success: string;
      successBg: string;
      successText: string;
      error: string;
      errorBg: string;
      errorText: string;
      warning: string;
      warningBg: string;
      warningText: string;
    };
    typography: {
      fontFamily: string;
      headingFontFamily: string;
      scale: {
        h1: TypographySpec;
        h2: TypographySpec;
        h3: TypographySpec;
        h4: TypographySpec;
        h5: TypographySpec;
        h6: TypographySpec;
        body1: TypographySpec;
        body2: TypographySpec;
        caption: TypographySpec;
      };
    };
    spacing: { xs: string; sm: string; md: string; lg: string; xl: string; xxl: string };
    borderRadius: { none: string; sm: string; md: string; lg: string; xl: string; full: string };
    shadows: { none: string; subtle: string; card: string; elevated: string };
    zIndex: { base: number; raised: number; dropdown: number; sticky: number; modal: number; toast: number };
  }

  export interface VellumApiConfig {
    baseUrl: string;
    getAccessToken: () => Promise<string>;
    endpoints?: Partial<{
      graphql: string;
      dynamic: string;
      negotiation: string;
      seal: string;
      agent: string;
      identity: string;
    }>;
  }

  export interface VellumProviderProps {
    theme: VellumTheme;
    apiConfig: VellumApiConfig;
    children: ReactNode;
  }

  export function VellumProvider(props: VellumProviderProps): JSX.Element;
  export function useVellum(): { theme: VellumTheme; apiConfig: VellumApiConfig };
  export function useVellumApi(): VellumApiConfig;
  export function useVellumTheme(): VellumTheme;
}

declare module '@vellum/ui/schema' {
  import { ReactNode } from 'react';

  export type FieldType = 'string' | 'number' | 'date' | 'datetime' | 'enum' | 'boolean' | 'party' | 'document' | 'json';

  export interface FieldUIConfig {
    type: FieldType;
    label?: string;
    placeholder?: string;
    required?: boolean;
    readOnly?: boolean;
    options?: Array<{ value: string; label: string }>;
    customRenderer?: (props: unknown) => ReactNode;
  }

  export interface SectionConfig {
    id: string;
    title: string;
    fields: string[];
    collapsible?: boolean;
  }

  export interface ColumnConfig {
    fieldPath: string;
    header: string;
    width?: number;
    sortable?: boolean;
    filterable?: boolean;
    cellRenderer?: (props: unknown) => ReactNode;
  }

  export interface EntityUIConfig {
    typeName: string;
    sections: SectionConfig[];
    fields: Record<string, FieldUIConfig>;
    columns?: ColumnConfig[];
    negotiableFields?: string[];
  }
}

declare module '@vellum/ui/negotiation' {
  export type FieldNegotiationStatus = 'DRAFT' | 'PROPOSED' | 'COUNTER_PROPOSED' | 'DISCREPANCY' | 'AGREED' | 'LOCKED' | 'REJECTED';

  export interface FieldStatus {
    entityId: string;
    fieldPath: string;
    status: FieldNegotiationStatus;
  }

  export function useEntityNegotiation(opts: {
    entityId: string;
    pollInterval?: number;
  }): {
    fieldStatuses: Record<string, FieldNegotiationStatus>;
    loading: boolean;
    error: unknown;
    refresh: () => void;
    submitProposal: (req: unknown) => Promise<unknown>;
    acceptProposal: (id: string, req: unknown) => Promise<unknown>;
    rejectProposal: (id: string, req: unknown) => Promise<unknown>;
  };
}

declare module '@vellum/ui/tables' {
  import type { ColumnDef } from '@tanstack/react-table';
  import type { EntityUIConfig, ColumnConfig } from '@vellum/ui/schema';

  export function buildColumnDefs<T = unknown>(config: EntityUIConfig | ColumnConfig[]): ColumnDef<T>[];
}
