// Static import surface against dynamic capability trace.
//
// The component's import list says what the artifact is *wired to* and may
// therefore ask the host for. It does not say which of those the host is
// actually asked for during one typed call. This host answers the second
// question: it instantiates the core module with a logging implementation of
// every wasi_snapshot_preview1 function and records what gets called, split
// into start-up and the call itself.
//
// It also reads the result back by hand, from the layout documented in Abi.hs,
// which is an independent check on the guest's encoding: jco agreeing with the
// guest proves the generated bindings match; this agreeing proves the layout is
// what we think it is.
import { readFile } from 'node:fs/promises';

const WASI_EBADF = 8;

const called = new Map();
let phase = 'startup';
const record = (name) => {
  const key = `${phase}:${name}`;
  called.set(key, (called.get(key) ?? 0) + 1);
};

let memory;
const view = () => new DataView(memory.buffer);
const bytes = () => new Uint8Array(memory.buffer);

// Every import is stubbed; the handful the runtime genuinely needs behave, the
// rest report "no such file descriptor", which is the honest answer from a host
// that granted nothing.
const behaviours = {
  clock_time_get: (_id, _precision, out) => { view().setBigUint64(out, BigInt(Date.now()) * 1000000n, true); return 0; },
  environ_sizes_get: (count, size) => { view().setUint32(count, 0, true); view().setUint32(size, 0, true); return 0; },
  environ_get: () => 0,
  fd_write: (_fd, iovs, iovsLen, written) => {
    let total = 0;
    for (let i = 0; i < iovsLen; i++) {
      const ptr = view().getUint32(iovs + i * 8, true);
      const len = view().getUint32(iovs + i * 8 + 4, true);
      total += len;
      if (len > 0) process.stderr.write(Buffer.from(bytes().slice(ptr, ptr + len)));
    }
    view().setUint32(written, total, true);
    return 0;
  },
  fd_read: (_fd, _iovs, _iovsLen, read) => { view().setUint32(read, 0, true); return 0; },
  fd_seek: (_fd, _offset, _whence, out) => { view().setBigUint64(out, 0n, true); return 0; },
  fd_close: () => 0,
  poll_oneoff: (_in, _out, _n, events) => { view().setUint32(events, 0, true); return 0; },
  proc_exit: (code) => { throw new Error(`guest called proc_exit(${code})`); },
};

const imports = {};
for (const name of [
  'clock_time_get', 'environ_get', 'environ_sizes_get', 'fd_close', 'fd_fdstat_get',
  'fd_fdstat_set_flags', 'fd_filestat_get', 'fd_filestat_set_size', 'fd_prestat_dir_name',
  'fd_prestat_get', 'fd_read', 'fd_seek', 'fd_write', 'path_create_directory',
  'path_filestat_get', 'path_open', 'poll_oneoff', 'proc_exit',
]) {
  const behaviour = behaviours[name];
  imports[name] = (...args) => { record(name); return behaviour ? behaviour(...args) : WASI_EBADF; };
}

const core = await readFile(new URL('../build/validator-core.wasm', import.meta.url));
const { instance } = await WebAssembly.instantiate(core, { wasi_snapshot_preview1: imports });
const x = instance.exports;
memory = x.memory;

x._initialize();

phase = 'call';

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function lower(text) {
  const encoded = encoder.encode(text);
  const ptr = x.cabi_realloc(0, 0, 4, Math.max(encoded.length, 1));
  bytes().set(encoded, ptr);
  return [ptr, encoded.length];
}

const readString = (ptr, len) => decoder.decode(bytes().slice(ptr, ptr + len));

// The layout from Abi.hs, decoded here independently of jco.
function lift(ret) {
  const dv = view();
  if (dv.getUint8(ret) === 0) {
    return {
      ok: {
        displayedTarget: readString(dv.getUint32(ret + 4, true), dv.getUint32(ret + 8, true)),
        quote: readString(dv.getUint32(ret + 12, true), dv.getUint32(ret + 16, true)),
      },
    };
  }
  const errCase = dv.getUint8(ret + 4);
  if (errCase === 0) {
    return { err: { tag: 'unknown-item', val: readString(dv.getUint32(ret + 8, true), dv.getUint32(ret + 12, true)) } };
  }
  return { err: { tag: errCase === 1 ? 'blank-evidence' : 'not-exact-span' } };
}

function validate(languageIndex, itemId, quote) {
  const [itemPtr, itemLen] = lower(itemId);
  const [quotePtr, quoteLen] = lower(quote);
  const ret = x.validate_evidence(languageIndex, itemPtr, itemLen, quotePtr, quoteLen);
  const lifted = lift(ret);
  x.cabi_post_validate_evidence(ret);
  return lifted;
}

// Every branch, not only the happy one: an accepted span, both rejections, the
// unknown item, and the cross-language case. If any of them reaches for the
// host, this is where it shows up.
const vectors = [
  [0, 'dg-04', 'оставил окно открытым'],
  [0, 'dg-04', 'забыл закрыть окно'],
  [0, 'dg-04', '   '],
  [0, 'nope', 'x'],
  [1, 'dg-04', 'оставил окно открытым'],
  [1, 'dg-04', 'left the window open'],
];
for (const [language, itemId, quote] of vectors) {
  console.log(`  ${JSON.stringify(quote).padEnd(26)} -> ${JSON.stringify(validate(language, itemId, quote))}`);
}

const startup = [...called.keys()].filter((k) => k.startsWith('startup:')).map((k) => k.slice(8)).sort();
const duringCall = [...called.keys()].filter((k) => k.startsWith('call:')).map((k) => k.slice(5)).sort();

console.log(`\nstatic preview1 import surface : 18`);
console.log(`touched during _initialize     : ${startup.length}  ${startup.join(' ') || '(none)'}`);
console.log(`touched across all six calls   : ${duringCall.length}  ${duringCall.join(' ') || '(none)'}`);
