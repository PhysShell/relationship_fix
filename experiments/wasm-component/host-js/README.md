# JavaScript hosts

Two of them, answering different questions. Neither knows the implementation
language.

## `host.mjs` — the typed interface

    npm install @bytecodealliance/jco
    npx jco transpile ../relationship-fix-validator.component.wasm -o out --name validator
    npm pkg set type=module
    node host.mjs

`jco` derives the bindings from the WIT alone, including the record and the
tagged variant, and maps `result<T, E>` onto "return `T`, or throw with
`.payload = E`".

## `trace.mjs` — the dynamic capability trace

    node trace.mjs

No dependencies: it instantiates `../build/validator-core.wasm` directly with a
logging implementation of all eighteen `wasi_snapshot_preview1` functions, then
lowers the parameters and lifts the result by hand from the layout documented in
`Abi.hs`. It answers what an execution actually asked the host for, which the
import list cannot, and its by-hand decoding independently checks the guest's
encoding against jco's.
