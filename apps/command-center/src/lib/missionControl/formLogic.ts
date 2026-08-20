/**
 * Pure logic behind `MissionControlPanel` — client-side validation for the
 * create+authorize form and API-error-to-display-string formatting. Split out of the
 * component (which is `.tsx`/JSX) so it can be imported and tested directly with Node's
 * built-in TypeScript stripping (`node --experimental-strip-types`), without a JSX
 * toolchain — see `scripts/check-mission-control-client.mjs` and
 * `scripts/check-mission-control-form.mjs`.
 */

import { ApiError } from '../api/client.ts';
import { sanitizeDisplayText } from '../security/renderSafety.mjs';
import type { LanguageAdapter } from '../api/client.ts';

export interface FormState {
  name: string;
  repositoryRef: string;
  adapter: LanguageAdapter;
  grantedBy: string;
  statement: string;
  validForMinutes: number;
}

export function defaultForm(): FormState {
  return {
    name: '',
    repositoryRef: '',
    adapter: 'C_CMAKE_CTEST',
    grantedBy: '',
    statement: '',
    validForMinutes: 240,
  };
}

/**
 * Mirrors the server-side field constraints exactly (`contracts/schemas/missions.py`:
 * `MissionCreateRequest.name` 1–200 chars, `repository_ref` 1–500,
 * `AuthorizationRequest.statement` 20–4000, `granted_by` 1–200,
 * `valid_for_minutes` 1–1440) so a client-side rejection and a server-side one never
 * disagree about what is valid.
 */
export function validateForm(form: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (form.name.trim().length < 1 || form.name.length > 200) {
    errors.name = 'name is required, up to 200 characters.';
  }
  if (form.repositoryRef.trim().length < 1 || form.repositoryRef.length > 500) {
    errors.repositoryRef = 'repository reference is required, up to 500 characters.';
  }
  if (form.grantedBy.trim().length < 1 || form.grantedBy.length > 200) {
    errors.grantedBy = 'the accountable human is required, up to 200 characters.';
  }
  if (form.statement.trim().length < 20 || form.statement.length > 4000) {
    errors.statement = 'authorization statement must be at least 20 characters.';
  }
  if (!Number.isFinite(form.validForMinutes) || form.validForMinutes < 1 || form.validForMinutes > 1440) {
    errors.validForMinutes = 'authorization lifetime must be 1 to 1440 minutes.';
  }
  return errors;
}

export interface DisplayError {
  message: string;
  code: string;
  traceId: string | null;
}

/** Turns any thrown value into display-safe copy. Server-supplied text (`ApiError.message`,
 * `.details`) is run through `sanitizeDisplayText` before it ever reaches JSX, same discipline
 * as every other server-derived string in this app (`src/lib/security/renderSafety.mjs`). */
export function describeApiError(error: unknown): DisplayError {
  if (error instanceof ApiError) {
    const detailBits = Object.entries(error.details)
      .filter(([key]) => key !== 'errors')
      .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
      .join(', ');
    const message = detailBits ? `${error.message} (${detailBits})` : error.message;
    return {
      message: sanitizeDisplayText(message, { fallback: 'Control API rejected the request.', maxLength: 400 }),
      code: error.code,
      traceId: error.traceId,
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return {
    message: sanitizeDisplayText(message, { fallback: 'Unexpected client error.', maxLength: 400 }),
    code: 'CLIENT',
    traceId: null,
  };
}
