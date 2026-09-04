// A JavaScript host calling a Haskell component through a typed WIT interface.
// No stdin, no stdout protocol, no JSON: a function call, a record back, and a
// tagged variant on failure.
import { validator } from './out/validator.js';

// jco maps result<T, E> onto "return T, or throw with .payload = E".
function call(language, itemId, quote) {
  try {
    return { ok: validator.validateEvidence(language, itemId, quote) };
  } catch (thrown) {
    return { err: thrown.payload ?? thrown };
  }
}

const show = (r) =>
  r.ok ? `ok(${JSON.stringify(r.ok.quote)} of ${JSON.stringify(r.ok.displayedTarget.slice(0, 28) + '…')})`
       : `err(${r.err.tag}${r.err.val !== undefined ? `(${JSON.stringify(r.err.val)})` : ''})`;

const vectors = [
  ['ru', 'dg-04', 'оставил окно открытым', (r) => r.ok?.quote === 'оставил окно открытым'
      && r.ok.displayedTarget.startsWith('Ты вчера'),                'exact RU span accepted, with the RU target'],
  ['ru', 'dg-04', 'забыл закрыть окно',    (r) => r.err?.tag === 'not-exact-span',  'RU paraphrase is not a span'],
  ['ru', 'dg-04', '   ',                   (r) => r.err?.tag === 'blank-evidence',  'blank is told apart from wrong'],
  ['ru', 'nope',  'x',                     (r) => r.err?.tag === 'unknown-item' && r.err.val === 'nope',
                                                                                    'unknown item carries its id'],
  ['en', 'dg-04', 'оставил окно открытым', (r) => r.err?.tag === 'not-exact-span',  'RU span is not a span of the EN presentation'],
  ['en', 'dg-04', 'left the window open',  (r) => r.ok?.quote === 'left the window open'
      && r.ok.displayedTarget.startsWith('You left'),               'exact EN span accepted, with the EN target'],
];

let failed = 0;
for (const [language, item, quote, expect, name] of vectors) {
  const result = call(language, item, quote);
  const ok = expect(result);
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}\n        ${show(result)}`);
}
console.log(failed === 0
  ? 'javascript host: all vectors agree with the Haskell rules'
  : `javascript host: ${failed} disagreement(s)`);
process.exit(failed === 0 ? 0 : 1);
