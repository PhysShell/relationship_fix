# JavaScript host

Calls the Haskell component through the typed WIT interface. Nothing here knows
the implementation language.

    npm install @bytecodealliance/jco
    npx jco transpile ../relationship-fix-validator.component.wasm -o out --name validator
    npm pkg set type=module
    node host.mjs

`jco` generates this from the WIT alone:

    export function validateEvidence(language: Language, itemId: string, quote: string): boolean;
    export type Language = 'ru' | 'en';
