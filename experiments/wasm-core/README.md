# Protocol core on wasm32-wasi

A laboratory build, not part of the deployed instrument. Nothing in
`src/annotation-web/` depends on it and CI does not build it.

It compiles the very same `Domain` and `Catalog` modules that the Yesod
application uses — no fork, no second copy of the rules — to `wasm32-wasi`, and
runs them under Wasmtime with no HTTP, no SQLite, no filesystem and no network.

## Why bother

The interesting question is not image size. It is where the trust boundary sits.

A native process is born holding the filesystem, the network, the clock and the
environment, and we then spend systemd directives taking those back:
`ProtectSystem=strict`, `PrivateTmp=true`, `ProtectKernelTunables=true`. The
boundary is subtractive, and whatever you forgot to subtract is still there.

A WASI guest starts holding nothing and is handed capabilities one at a time.
The boundary is additive, and what the module can even ask for is a finite list
you can print.

## Build

Needs the official GHC WebAssembly backend, which is a **separate cross
compiler**, not the GHC that builds the application:

    curl https://gitlab.haskell.org/haskell-wasm/ghc-wasm-meta/-/raw/master/bootstrap.sh | sh
    . ~/.ghc-wasm/env
    sh experiments/wasm-core/build.sh

`Domain.hs` takes `GHC2021` and `DerivingStrategies` from the package's
`default-extensions`, so the direct compiler invocation in `build.sh` passes
them explicitly.

## Run

    wasmtime run relationship-fix-core.wasm contract
    wasmtime run relationship-fix-core.wasm selftest
    wasmtime run relationship-fix-core.wasm validate ru dg-04 "оставил окно открытым"
    wasmtime run relationship-fix-core.wasm read /etc/hostname
    wasmtime run --dir /etc relationship-fix-core.wasm read /etc/hostname

## Measured, 2026-09-04

    wasm32-wasi-ghc   9.14.1.20260731
    wasmtime          48.0.0
    wasi-sdk          29.0
    build             1.7 s
    module            2.05 MiB
    WASI imports      20, all from wasi_snapshot_preview1
    network imports   0

The ten protocol invariants the native hspec suite asserts also pass when
compiled to a different instruction set by a different compiler.

### The capability surface, literally

The module imports exactly twenty functions: `args_get`, `args_sizes_get`,
`clock_time_get`, `environ_get`, `environ_sizes_get`, `fd_close`,
`fd_fdstat_get`, `fd_fdstat_set_flags`, `fd_filestat_get`,
`fd_filestat_set_size`, `fd_prestat_dir_name`, `fd_prestat_get`, `fd_read`,
`fd_seek`, `fd_write`, `path_create_directory`, `path_filestat_get`,
`path_open`, `poll_oneoff`, `proc_exit`.

There is no `sock_accept`, no `sock_recv`, no `sock_send`. This module cannot
open a socket — not "is not permitted to", but has no instruction that reaches
one. That is a property of the artifact, checkable with `wasm-dis`, rather than
a property of a policy file somewhere on the host.

### Denial by default is not a permission error

    $ wasmtime run core.wasm read /etc/hostname
    denied:  /etc/hostname: openFile: does not exist

    $ wasmtime run --dir /etc core.wasm read /etc/hostname
    granted: 3 bytes from /etc/hostname

The same module, one more capability. Note the first message: not "permission
denied" but "does not exist". An ungranted path is not forbidden, it is absent
from the guest's namespace. There is nothing to probe for.

### A bug the unit tests could not have found

The first native run crashed on the first Cyrillic character:
`commitAndReleaseBuffer: invalid argument (cannot encode character '\1058')`.
Handle encodings are derived from the ambient locale, and a CI runner, a systemd
unit and a WASI guest all have none. A bilingual instrument whose output depends
on the operator's `LANG` is broken; `Main.hs` now sets the encoding explicitly
for stdout, stderr and argument decoding. The hspec suite never saw it because
tests do not write the instrument's own output.

## What this does not show

**The application cannot follow.** Warp needs sockets, `persistent-sqlite`
needs the SQLite C library through FFI, and neither is reachable from the import
list above. Porting the server would mean re-hosting it on `wasi:http` and
replacing storage — a rewrite, not a retarget.

**The compiler is not the same one.** The application is built with GHC 9.10.3
(Stackage LTS 24.57). The WebAssembly backend here is a 9.14.1 development
snapshot living in its own tree. The backend is a tech preview; treat divergence
between the two builds as expected, and this directory as a lab rather than a
second production target.

**Only step three of five.** The ladder was: native + systemd sandbox → OS
container → Wasm command → Wasm component with a typed WIT interface → host
granting explicit capabilities. This is the Wasm command. The Component Model
step, where the validator becomes a typed component callable from other
languages, is the one worth doing next and is not done here.
