# The evidence rule as a Component Model component

A laboratory build, like `../wasm-core`. Nothing in `src/annotation-web/`
depends on it and CI does not build it.

Where `../wasm-core` produced a WASI **command** that a human runs and whose
answers arrive as text on stdout, this produces a **component** with a typed
interface that another program calls. The rules are the same Haskell.

## The interface

`wit/validator.wit` declares a package, an enum and one function:

    validate-evidence: func(language: language, item-id: string, quote: string) -> bool

That signature is part of the artifact. A caller does not parse output, does not
agree on a JSON shape, and does not know the implementation language. Running
`jco transpile` over the component produces, from the WIT alone:

    export function validateEvidence(language: Language, itemId: string, quote: string): boolean;
    export type Language = 'ru' | 'en';

## Acceptance, as required

1. `wasm-tools validate --features component-model` — passes.
2. `wasm-tools component wit` reports `export relationship-fix:annotation/validator@0.1.0`,
   not merely `wasi:cli/run`.
3. A JavaScript host calls `validateEvidence` directly; see `host-js/`. No
   stdin, no stdout protocol, no JSON.
4. The vectors agree from both hosts:

        validate-evidence(ru, "dg-04", "оставил окно открытым")  -> true
        validate-evidence(ru, "dg-04", "забыл закрыть окно")     -> false
        validate-evidence(en, "dg-04", "оставил окно открытым")  -> false
        validate-evidence(en, "dg-04", "left the window open")   -> true
        validate-evidence(ru, "dg-04", "   ")                    -> false
        validate-evidence(ru, "no-such-item", "…")               -> false

   The third line is the point of the whole instrument: the same quote is valid
   against a Russian presentation and invalid against the English translation,
   and that survives the crossing into a foreign type system.
5. `Domain.hs` and `Catalog.hs` are untouched and contain no occurrence of
   wasm, WASI, component, WIT, Wasmtime or ABI. `validEvidence` is defined once
   and called from the server, the tests, the CLI experiment and `Abi.hs`.

## Measured, 2026-09-04

    wasm32-wasi-ghc   9.14.1.20260731
    wasm-tools        1.257.1
    wasmtime          48.0.0
    jco               via npm, node v26.8.1
    core reactor      2 193 014 bytes
    component         1 781 651 bytes

## Three things that had to be worked around

These are the answer to "how hard is it today to make a Haskell guest a real
component without duplicating domain logic". The answer is: possible, with
three pieces of glue, none of which contains a rule.

**GHC cannot name a canonical export.** The component ABI wants the core module
to export `relationship-fix:annotation/validator@0.1.0#validate-evidence`. GHC
answers:

    ‘relationship-fix:annotation/validator@0.1.0#validate-evidence’
    is not a valid C identifier

`foreign export ccall` demands a valid C identifier; WIT names are kebab-case
and canonical names carry `:`, `/`, `@` and `#`. The intersection of the two
grammars is empty, so `build.sh` renames one export through a text round-trip.
It is a rename and nothing else.

**`cabi_realloc` cannot be Haskell.** The first attempt implemented it with
`mallocBytes`/`reallocBytes` and trapped:

    newBoundTask -> errorBelch -> vfprintf -> __wasi_fd_write
      -> adapter fd_write -> allocate_stack -> cabi_realloc
        -> rts_lock -> newBoundTask -> stg_exit -> proc_exit
    wasm trap: cannot leave component instance

The canonical ABI calls `cabi_realloc` from inside the WASI adapter, including
while servicing `fd_write`. A Haskell implementation re-enters the RTS at
exactly the moments it is not ready; the RTS reports that through stderr, which
re-enters the adapter, which calls the allocator again. It is plain C over
wasi-libc now.

**A reactor does not start the RTS.** `_initialize` runs the wasm constructors
and brings up libc, and then the first typed call dies with
`newBoundTask: RTS is not initialised; call hs_init() first`. A command module
gets this from `_start`; a reactor has to ask, so `cabi_realloc.c` calls
`hs_init` from a constructor.

## The result that surprised us

Moving from a CLI command to a typed component removes exactly **two** WASI
imports: `args_get` and `args_sizes_get`.

    command module   20 preview1 imports
    reactor module   18 preview1 imports
    difference       args_get, args_sizes_get

Everything else — the filesystem calls, the clock, stdio — is imported by the
GHC runtime, not by the annotation code. Neither build imports any `sock_*`,
and the lifted component imports no `wasi:sockets` and no `wasi:http`.

So the capability surface of a Haskell guest today is dominated by its language
runtime rather than by its application. Narrowing the interface narrows what
callers may *ask for*; it does not by itself narrow what the module may *reach*.
Both facts matter, and only the first is the one people quote.

## Not attempted

Richer WIT shapes. `validate-evidence` returns a bare `bool` because the
canonical ABI flattens it into a single `i32` result, needing neither a return
pointer nor `cabi_post_return`. The record-and-`result<>` interface in the
original sketch requires lifting and lowering those by hand in Haskell, since
`wit-bindgen` has no Haskell backend. That is the next honest step, and it is
also where hand-writing the ABI stops being a weekend exercise.
