// ESLint flat config for the whole repository.
//
// Scope note: this is REPOSITORY-ROOT tooling. apps/command-center/ is owned by the
// frontend developer and does not exist as of D1; when it lands, its files are picked up
// by the globs below without any change here. If that developer needs project-specific
// rules, an eslint.config.js inside apps/command-center/ takes precedence — flat config
// resolves to the nearest one.
//
// Type-aware linting (typescript-eslint's `recommendedTypeChecked`) is deliberately NOT
// enabled. It needs a tsconfig.json that does not exist yet and roughly triples lint time.
// Revisit once the Astro app has one; noted as an open question in the D1 handoff.

import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import astro from 'eslint-plugin-astro';

export default [
  {
    ignores: [
      '**/node_modules/**',
      '**/dist/**',
      '**/.astro/**',
      '**/.venv/**',
      'demo/repositories/**', // vulnerable-by-design fixtures; not ours to lint
      'infrastructure/compose/nginx/**',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,

  {
    files: ['**/*.{js,mjs,cjs,ts,tsx,astro}'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // The Command Center displays real telemetry only (CLAUDE.md). A stray console
      // statement in a client island is noise in an operator's browser during a demo;
      // warn and error are kept because they carry real failures.
      'no-console': ['warn', { allow: ['warn', 'error'] }],

      // An unused variable prefixed with _ is an explicit "yes, I know".
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-var': 'error',
      'prefer-const': 'error',
    },
  },

  {
    // Node-only tooling scripts.
    files: ['infrastructure/scripts/**/*.mjs', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
    rules: { 'no-console': 'off' },
  },
];
