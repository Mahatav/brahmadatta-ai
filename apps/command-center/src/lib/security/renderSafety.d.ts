export interface DisplayTextOptions {
  fallback?: string;
  maxLength?: number;
  preserveWhitespace?: boolean;
}

export interface DisplayListOptions extends DisplayTextOptions {
  maxItems?: number;
}

export const DEFAULT_DISPLAY_MAX_LENGTH: number;
export const DEFAULT_REPORT_MAX_LENGTH: number;
export const TRUNCATED_MARKER: string;

export function sanitizeDisplayText(value: unknown, options?: DisplayTextOptions): string;
export function sanitizeDisplayList(values: unknown, options?: DisplayListOptions): string[];
export function sanitizeJsonReportValue(value: unknown, options?: DisplayTextOptions): string;
export function sanitizeMarkdownText(value: unknown, options?: DisplayTextOptions): string;
