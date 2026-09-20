#!/usr/bin/env node
import { readFileSync, globSync } from 'node:fs';

const PALETTES =
  'slate|gray|zinc|neutral|stone|indigo|violet|purple|blue|sky|cyan|teal|' +
  'emerald|green|lime|yellow|amber|orange|red|rose|pink|fuchsia';
const PREFIXES =
  'bg|text|border|ring|shadow|from|to|via|divide|placeholder|decoration|' +
  'outline|accent|fill|stroke';

// Chrome hexes main.tsx already uses, plus #000000 which is the
// --color-surface-container-lowest token from index.css.
const ALLOWED_HEX = new Set([
  '#000000', '#0e0e0e', '#131313', '#191a1a', '#252626', '#484848', '#c6c6c7',
]);

// The landing and auth pages predate phase 1, are part of the approved main
// design, and use a deliberate glow treatment the terminal shell does not.
// They are outside this restoration's scope. Remove an entry here only
// alongside reskinning that page.
const EXCLUDED = ['src/pages/Landing.tsx', 'src/pages/Auth.tsx'];

const RULES = [
  {
    name: 'off-palette colour',
    re: new RegExp(`\\b(?:${PREFIXES})-(?:${PALETTES})-[0-9]{2,3}\\b`, 'g'),
  },
  // rounded-none and shadow-none enforce the system rather than violate it.
  { name: 'border radius (system is 0px)', re: /\brounded(?!-none\b)(?:-[a-z0-9]+)*\b/g },
  { name: 'shadow (system is flat)', re: /\bshadow-(?!none\b)[a-z0-9/[\]_-]+/g },
  { name: 'backdrop blur (system is flat)', re: /\bbackdrop-blur[a-z-]*/g },
  { name: 'gradient (system is flat)', re: /\bbg-gradient-[a-z-]+/g },
  { name: 'font-mono (use font-label)', re: /\bfont-mono\b/g },
];

const HEX_RE = /#[0-9a-fA-F]{6}\b/g;

const norm = (p) => p.replace(/\\/g, '/');

const files = (
  process.argv.length > 2
    ? process.argv.slice(2)
    : globSync('src/**/*.tsx', { cwd: process.cwd() })
).filter((f) => {
  const n = norm(f);
  return !n.includes('.test.') && !EXCLUDED.includes(n);
});

let violations = 0;

for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');

  lines.forEach((line, i) => {
    for (const { name, re } of RULES) {
      re.lastIndex = 0;
      for (const m of line.matchAll(re)) {
        console.error(`${norm(file)}:${i + 1}  ${name}: ${m[0]}`);
        violations++;
      }
    }
    for (const m of line.matchAll(HEX_RE)) {
      if (!ALLOWED_HEX.has(m[0].toLowerCase())) {
        console.error(`${norm(file)}:${i + 1}  unapproved hex: ${m[0]}`);
        violations++;
      }
    }
  });
}

if (violations > 0) {
  console.error(`\n${violations} design-system violation(s).`);
  process.exit(1);
}
console.log(`Design system clean (${files.length} file(s) checked).`);
