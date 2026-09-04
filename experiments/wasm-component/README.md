# The evidence rule as a Component Model component

A laboratory build, like `../wasm-core`. Nothing in `src/annotation-web/`
depends on it and CI does not build it.

Where `../wasm-core` produced a WASI **command** that a human runs and whose
answers arrive as text on stdout, this produces a **component** with a typed
interface that another program calls. The rules are the same Haskell.

## The interface

`wit/validator.wit` declares `relationship-fix:annotation@0.2.0`:

    variant validation-error { unknown-item(string), blank-evidence, not-exact-span }
    record accepted-evidence { displayed-target: string, quote: string }

    validate-evidence: func(language: language, item-id: string, quote: string)
        -> result<accepted-evidence, validation-error>

The first version of this experiment returned a bare `bool`. That was a mistake
worth making once: the canonical ABI flattens a `bool` into a single scalar and
hands it back in a register, so none of the machinery the Component Model is
made of was ever exercised. This signature returns owned strings inside a
record inside a `result`, which does not fit in a register and therefore drags
in guest allocation, an indirect result and a post-return.

Running `jco transpile` over the component produces, from the WIT alone:

    export function validateEvidence(language: Language, itemId: string, quote: string): AcceptedEvidence;
    export type ValidationError = ValidationErrorUnknownItem | ValidationErrorBlankEvidence | ValidationErrorNotExactSpan;
    export interface AcceptedEvidence { displayedTarget: string, quote: string }

## Three different surfaces, which are easy to confuse

This is the distinction the experiment exists to make.

| | what it answers | measured |
|---|---|---|
| WIT interface surface | what a caller may ask us to do | 1 function |
| static WASI import surface | what the artifact is wired to and *may* ask the host for | 18 preview1 functions, lifted to 17 typed WASI interfaces |
| dynamic capability trace | what an execution *actually* asked for | 2 at start-up, 0 across all six calls |

An import list is an upper bound on reachable host calls, not a proof that each
one is reachable from `validate-evidence`. Proving the latter needs either a
reachability analysis over the call graph or an instrumented host. `host-js/trace.mjs`
is the instrumented host: it implements all eighteen `wasi_snapshot_preview1`
functions as logging stubs — the handful the runtime genuinely needs behave, the
rest return `EBADF`, which is the honest answer from a host that granted nothing
— and reports what was touched.

    static preview1 import surface : 18
    touched during _initialize     : 2  clock_time_get environ_sizes_get
    touched across all six calls   : 0  (none)

So the filesystem imports are cold runtime paths. The typed call itself, on every
branch including the failures, asks the host for nothing at all. That is a much
stronger statement than the import list alone supports, and it is only true
because it was measured; it is not deducible from the WIT.

The honest residue: this is one binary, one set of inputs and one execution.
It does not prove those paths are unreachable, only that nothing reached them
here.

## Acceptance, as required

1. `wasm-tools validate --features component-model` — passes.
2. `wasm-tools component wit` reports `export relationship-fix:annotation/validator@0.2.0`
   with the variant and the record, not merely `wasi:cli/run`.
3. A JavaScript host calls `validateEvidence` directly; see `host-js/`. No
   stdin, no stdout protocol, no JSON.
4. The vectors agree from three independent readers — Wasmtime's WAVE
   invocation, jco's generated bindings, and the by-hand decoder in
   `host-js/trace.mjs`:

        (ru, "dg-04", "оставил окно открытым") -> ok({displayed-target: "Ты вчера…", quote: "оставил окно открытым"})
        (ru, "dg-04", "забыл закрыть окно")    -> err(not-exact-span)
        (ru, "dg-04", "   ")                   -> err(blank-evidence)
        (ru, "nope",  "x")                     -> err(unknown-item("nope"))
        (en, "dg-04", "оставил окно открытым") -> err(not-exact-span)
        (en, "dg-04", "left the window open")  -> ok({displayed-target: "You left…", quote: "left the window open"})

   The fifth line is the point of the whole instrument: the same quote is valid
   against a Russian presentation and invalid against the English translation,
   and that survives the crossing into a foreign type system.
5. `Domain.hs` and `Catalog.hs` contain no occurrence of wasm, WASI, component,
   WIT, Wasmtime or ABI, and `checkEvidence` is defined once. The richer
   interface needed a distinction the domain had not yet drawn — a blank answer
   against a wrong one — so `checkEvidence` was added to `Domain.hs` and
   `validEvidence` re-expressed in terms of it. The rule moved into the domain
   rather than into this adapter, which is the direction the constraint
   requires; the application still builds and its suite still passes.

## Measured, 2026-09-04

    wasm32-wasi-ghc   9.14.1.20260731     (the application is built by GHC 9.10.3)
    wasm-tools        1.257.1
    wasmtime          48.0.0
    core reactor      2 245 310 bytes
    component         1 819 492 bytes
    transport glue    72 lines of Haskell, 60 lines of C

## What the canonical ABI cost, by hand

`wit-bindgen` has no Haskell backend, so every mechanism below was written out.
None of it contains a protocol rule.

**GHC cannot name a canonical export.** The ABI wants the core module to export
`relationship-fix:annotation/validator@0.2.0#validate-evidence`. GHC answers:

    ‘relationship-fix:annotation/validator@0.2.0#validate-evidence’
    is not a valid C identifier

`foreign export ccall` demands a valid C identifier; WIT names are kebab-case
and canonical names carry `:`, `/`, `@` and `#`. The intersection of the two
grammars is empty, so `build.sh` renames two exports — the function and its
post-return — through a text round-trip.

**`cabi_realloc` cannot be Haskell.** Implemented with `mallocBytes` it trapped:

    newBoundTask -> errorBelch -> vfprintf -> __wasi_fd_write
      -> adapter fd_write -> allocate_stack -> cabi_realloc
        -> rts_lock -> newBoundTask -> stg_exit -> proc_exit
    wasm trap: cannot leave component instance

The ABI calls the allocator from inside the WASI adapter, including while
servicing `fd_write`. A Haskell implementation re-enters the RTS at exactly the
moments it is not ready, the RTS reports that through stderr, and the report
re-enters the adapter. It is plain C over wasi-libc now.

**A reactor does not start the RTS.** `_initialize` runs the wasm constructors
and brings up libc, and then the first typed call dies with
`newBoundTask: RTS is not initialised`. A command gets this from `_start`; a
reactor has to ask, so `cabi_realloc.c` calls `hs_init` from a constructor.

**The layout is yours to compute.** `result<accepted-evidence, validation-error>`
is 20 bytes at alignment 4 — a one-byte discriminant padded to four, then the
larger of a 16-byte record of two strings and a 12-byte variant. Five flattened
i32 results exceed the one the ABI returns in a register, so it travels through
a pointer, which `cabi_post_validate_evidence` frees along with every string it
points at.

**Ownership bites, and quietly.** The host lowers the parameter strings into
guest memory using the guest's own allocator and has no way to release them, so
they are the guest's to free. Freeing them exposed this:

    validate-evidence(ru, "dg-04", "оставил окно открытым")
      -> err(unknown-item("\u{0}\u{0}\u{0}\u{0}\u{0}"))

Right length, all zero bytes. `decodeUtf8 <$> unsafePackCStringLen` shares the
host's buffer and defers the decode into a thunk; freeing the parameter left the
decode reading memory already handed back to the allocator. Because that memory
is recycled rather than unmapped, nothing crashed — the strings simply arrived
empty. Laziness and manual ownership do not mix by accident, and the fix is a
copy plus an `evaluate` before the free.

That last one is the real answer to "how hard is this today". Not the pointer
arithmetic, which is tedious but mechanical. The hazard is that a language with
non-strict evaluation and a garbage collector has to reason explicitly about
lifetimes it normally never mentions, at a boundary where the failure mode is
silence.

## Where this stops

Yesod is not going to WASI HTTP. That is a different server rather than a
retarget: Warp, Persistent and SQLite would all have to be replaced to prove
that a week can be spent. The ladder as it stands already shows what the
architecture buys, from one `checkEvidence`:

    native Haskell domain
        ├── Yesod production server
        ├── native hspec suite
        ├── wasm32-wasi command
        └── Component Model typed API, called from JavaScript
