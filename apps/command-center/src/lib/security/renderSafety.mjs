const ANSI_ESCAPE_PATTERN = new RegExp(
  String.raw`[\u001B\u009B][[\]()#;?]*(?:(?:(?:[a-zA-Z\d]*(?:;[a-zA-Z\d]*)*)?\u0007)|(?:(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))`,
  'g',
);
const CONTROL_PATTERN = new RegExp(String.raw`[\u0000-\u001F\u007F-\u009F]`, 'g');
const BIDI_OVERRIDE_PATTERN = new RegExp(String.raw`[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]`, 'g');
const COLLAPSED_WHITESPACE_PATTERN = /\s+/g;

export const DEFAULT_DISPLAY_MAX_LENGTH = 240;
export const DEFAULT_REPORT_MAX_LENGTH = 4000;
export const TRUNCATED_MARKER = '...[truncated]';

export function sanitizeDisplayText(value, options = {}) {
  const {
    fallback = 'unknown',
    maxLength = DEFAULT_DISPLAY_MAX_LENGTH,
    preserveWhitespace = false,
  } = options;

  const normalized = normalizeText(value, fallback, preserveWhitespace);
  return truncateText(normalized, maxLength);
}

export function sanitizeDisplayList(values, options = {}) {
  const { maxItems = 32, fallback = 'unknown', ...textOptions } = options;
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .slice(0, maxItems)
    .map((value) => sanitizeDisplayText(value, { fallback, ...textOptions }));
}

export function sanitizeJsonReportValue(value, options = {}) {
  return sanitizeDisplayText(value, {
    fallback: '',
    maxLength: DEFAULT_REPORT_MAX_LENGTH,
    preserveWhitespace: true,
    ...options,
  });
}

export function sanitizeMarkdownText(value, options = {}) {
  return escapeMarkdownHtml(sanitizeJsonReportValue(value, options));
}

function normalizeText(value, fallback, preserveWhitespace) {
  const initial = value == null ? '' : String(value);
  const stripped = initial
    .replace(ANSI_ESCAPE_PATTERN, '')
    .replace(BIDI_OVERRIDE_PATTERN, '')
    .replace(CONTROL_PATTERN, preserveWhitespace ? '\n' : ' ');
  const cleaned = preserveWhitespace ? stripped.trim() : stripped.replace(COLLAPSED_WHITESPACE_PATTERN, ' ').trim();
  return cleaned.length > 0 ? cleaned : fallback;
}

function truncateText(value, maxLength) {
  if (!Number.isFinite(maxLength) || maxLength <= 0 || value.length <= maxLength) {
    return value;
  }
  const visibleLength = Math.max(1, maxLength - TRUNCATED_MARKER.length);
  return `${value.slice(0, visibleLength)}${TRUNCATED_MARKER}`;
}

function escapeMarkdownHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`/g, '&#96;');
}
