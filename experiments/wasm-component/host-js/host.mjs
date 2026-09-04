// A JavaScript host calling a Haskell component through a typed WIT interface.
// No stdin, no stdout protocol, no JSON: a function call with a string return.
import { validator } from './out/validator.js';

const vectors = [
  ['ru', 'dg-04', 'оставил окно открытым',  true,  'exact RU span accepted'],
  ['ru', 'dg-04', 'забыл закрыть окно',     false, 'RU paraphrase rejected'],
  ['en', 'dg-04', 'оставил окно открытым',  false, 'RU span rejected against EN presentation'],
  ['en', 'dg-04', 'left the window open',   true,  'exact EN span accepted against EN presentation'],
  ['ru', 'dg-04', '   ',                    false, 'blank rejected'],
  ['ru', 'nope',  'оставил окно открытым',  false, 'unknown item rejected'],
];

let failed = 0;
for (const [lang, item, quote, expected, name] of vectors) {
  const actual = validator.validateEvidence(lang, item, quote);
  const ok = actual === expected;
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  (got ${actual})`);
}
console.log(failed === 0 ? 'javascript host: all vectors agree with the Haskell rules'
                         : `javascript host: ${failed} disagreement(s)`);
process.exit(failed === 0 ? 0 : 1);
