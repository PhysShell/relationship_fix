#!/usr/bin/env bash
# Ядро считается доказанным, только когда проходят ВСЕ слои. Они разные и
# ловят разное:
#
#   source policy      запрещённые конструкции в коде (не в комментариях)
#   import hygiene     дерево доказательств не импортирует Challenge
#   build              Lean-ядро проверило доказательства
#   statement integrity solution доказывает ЗАМОРОЖЕННЫЙ вопрос
#   final check        доверенная база прибита к исходнику (#guard_msgs)
#
# LEAN_PATH сбрасывается намеренно: иначе теорему можно «доказать» случайным
# .olean из соседней помойки и потом три часа искать привидений.
set -euo pipefail
unset LEAN_PATH
cd "$(dirname "$0")/.."

echo "== 1. source policy =="
python3 scripts/policy_scan.py

echo "== 2. import hygiene =="
if grep -rn "import RelationshipFix.Verification.Challenge" \
      RelationshipFix/TrustedSpec* RelationshipFix/Proofs* RelationshipFix.lean 2>/dev/null; then
  echo "FAIL: дерево доказательств импортирует Challenge — вопрос и ответ склеились"
  exit 1
fi
if grep -rn "import RelationshipFix.Proofs" RelationshipFix/Verification/Challenge.lean 2>/dev/null; then
  echo "FAIL: Challenge зависит от слоя доказательств"
  exit 1
fi
echo "  none"

echo "== 3. build =="
lake build

echo "== 4. statement integrity + final check =="
lake env lean RelationshipFix/Verification/FinalCheck.lean
echo "  ok"

echo
scripts/certificate.sh
