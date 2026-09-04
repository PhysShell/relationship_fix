#!/bin/sh
# Builds the evidence rule as a Component Model component with a typed WIT
# interface, from the same Domain and Catalog modules the application uses.
#
# Requires the GHC WebAssembly backend (which also ships wasm-tools and the
# wasi-sdk this script uses):
#
#   curl https://gitlab.haskell.org/haskell-wasm/ghc-wasm-meta/-/raw/master/bootstrap.sh | sh
#   . ~/.ghc-wasm/env
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
here=$root/experiments/wasm-component
build=${BUILD_DIR:-$here/build}
adapter=$build/wasi_snapshot_preview1.reactor.wasm
wasmtime_version=${WASMTIME_VERSION:-v48.0.0}
component=$here/relationship-fix-validator.component.wasm

mkdir -p "$build"

# 1. The Preview1-to-Component adapter, published with every Wasmtime release.
if [ ! -f "$adapter" ]; then
  curl -fsSL -o "$adapter" \
    "https://github.com/bytecodealliance/wasmtime/releases/download/$wasmtime_version/wasi_snapshot_preview1.reactor.wasm"
fi

# 2. The canonical ABI allocator and the RTS start-up, in C. The file explains
#    at length why neither of them can be Haskell.
"${CC:-wasm32-wasi-clang}" --target=wasm32-wasi -O2 \
  -c "$here/cabi_realloc.c" -o "$build/cabi_realloc.o"

# 3. A reactor rather than a command: no main, no _start, only typed exports.
wasm32-wasi-ghc \
  -XGHC2021 -XDerivingStrategies \
  -Wall -Werror \
  -no-hs-main -optl-mexec-model=reactor \
  -optl-Wl,--export=cabi_realloc \
  -optl-Wl,--export=validate_evidence \
  -optl-Wl,--export=cabi_post_validate_evidence \
  -i"$root/src/annotation-web/src" -i"$here" \
  -outputdir "$build/obj" \
  "$build/cabi_realloc.o" \
  -o "$build/validator-core.wasm" \
  "$here/Abi.hs"

# 4. Rename the export to its canonical WIT name.
#
#    This step exists because GHC refuses the name at source:
#
#      ‘relationship-fix:annotation/validator@0.1.0#validate-evidence’
#      is not a valid C identifier
#
#    foreign export ccall demands a valid C identifier, while every canonical
#    component export name contains ':', '/', '@', '#' -- and WIT names are
#    kebab-case, so even a bare function name is out of reach. The intersection
#    of the two grammars is empty. This renames one export and does nothing
#    else; no rule of the protocol passes through here.
wasm-tools print "$build/validator-core.wasm" -o "$build/core.wat"
canonical='relationship-fix:annotation/validator@0.2.0#validate-evidence'
sed -i \
  -e "s|(export \"validate_evidence\"|(export \"$canonical\"|" \
  -e "s|(export \"cabi_post_validate_evidence\"|(export \"cabi_post_$canonical\"|" \
  "$build/core.wat"
wasm-tools parse "$build/core.wat" -o "$build/validator-renamed.wasm"

# 5. Embed the WIT world, then lift the core module into a component.
wasm-tools component embed "$here/wit" --world annotation-validator \
  "$build/validator-renamed.wasm" -o "$build/validator-embedded.wasm"
wasm-tools component new "$build/validator-embedded.wasm" \
  --adapt "wasi_snapshot_preview1=$adapter" \
  -o "$component"

wasm-tools validate --features component-model "$component"
echo "built $component"
