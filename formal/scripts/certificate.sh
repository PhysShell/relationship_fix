#!/usr/bin/env bash
# Воспроизводимый сертификат. Печатает то, ЧТО именно было проверено:
# какой коммит, какой тулчейн, какие ВОПРОСЫ (их хэши) и какая доверенная
# база. Хэши TrustedSpec и Challenge здесь затем, чтобы правку вопроса
# нельзя было провести молча.
set -euo pipefail
unset LEAN_PATH
cd "$(dirname "$0")/.."

digest() { sha256sum "$@" | awk '{print substr($1,1,16), $2}'; }

echo "PROOF CERTIFICATE"
echo "  git_commit      $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "  git_dirty       $(git status --porcelain -- . | wc -l) changed files under formal/"
echo "  lean_version    $(lean --version | head -1)"
echo "  toolchain       $(cat lean-toolchain)"
echo "  mathlib         none (core List.Perm only)"
echo
echo "  frozen question (TrustedSpec):"
digest RelationshipFix/TrustedSpec/*.lean | sed 's/^/    /'
echo "  challenge + gate:"
digest RelationshipFix/Verification/Challenge.lean \
       RelationshipFix/Verification/FinalCheck.lean \
       RelationshipFix/Verification/StatementIntegrity.lean | sed 's/^/    /'
echo
echo "  trusted base:"
lake env lean RelationshipFix/Verification/Audit.lean 2>/dev/null | sed 's/^/    /'
echo
echo "  NOT DONE HERE: upstream leanprover/comparator (separate environments +"
echo "  kernel replay) and a second independent kernel. See docs/formal-model.md."
