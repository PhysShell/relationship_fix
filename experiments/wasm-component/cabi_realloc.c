/* Canonical ABI allocator for the validator component.
 *
 * This cannot be written in Haskell. The Component Model calls cabi_realloc to
 * lower host values into guest memory, and the WASI adapter calls it from
 * inside its own machinery -- including while servicing fd_write. A Haskell
 * implementation enters the RTS at those moments, and when the RTS is not
 * ready it reports the failure through stderr, which re-enters the adapter,
 * which calls cabi_realloc again. That cascade traps with "cannot leave
 * component instance".
 *
 * So the allocator is plain C over wasi-libc: no runtime, no reentrancy, no
 * rules. It is transport, and nothing else.
 */
#include <stdlib.h>

/* The component instantiates the guest by calling _initialize, which runs the
 * wasm constructors and brings up libc -- but not the Haskell RTS. Without
 * this, the first typed call dies with "newBoundTask: RTS is not initialised".
 * A command module gets this for free from _start; a reactor has to ask.
 */
extern void hs_init(int *argc, char **argv[]);

__attribute__((constructor))
static void initialise_haskell_runtime(void) {
    hs_init(NULL, NULL);
}

__attribute__((export_name("cabi_realloc")))
void *cabi_realloc(void *ptr, size_t old_size, size_t align, size_t new_size) {
    (void)old_size;

    /* The canonical ABI permits a zero-sized allocation and still expects an
     * aligned, non-null pointer back; the alignment itself is a valid one. */
    if (new_size == 0) {
        return (void *)align;
    }

    void *fresh = realloc(ptr, new_size);
    if (fresh == NULL) {
        abort();
    }
    return fresh;
}

/* post-return for validate-evidence.
 *
 * Five flattened i32 results do not fit the single register the canonical ABI
 * will return, so the result travels through a pointer into our linear memory.
 * The host reads it and then calls this, which is the only chance anyone gets
 * to release the buffers the result points at.
 *
 * The layout is the one computed in Abi.hs. Walking it is transport, not a
 * rule: nothing here decides whether a quote was valid, only which pointers
 * exist to be freed.
 */
__attribute__((export_name("cabi_post_validate_evidence")))
void cabi_post_validate_evidence(unsigned char *result) {
    if (result == NULL) {
        return;
    }

    if (result[0] == 0) {
        /* ok(accepted-evidence): displayed-target at +4, quote at +12 */
        free(*(void **)(result + 4));
        free(*(void **)(result + 12));
    } else if (result[4] == 0) {
        /* err(unknown-item(string)): the payload string at +8 */
        free(*(void **)(result + 8));
    }

    free(result);
}
