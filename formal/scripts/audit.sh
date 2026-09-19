#!/bin/sh
# Ядро считается доказанным, только если:
#   1. собирается;
#   2. в исходниках нет sorry / axiom / unsafe / native_decide;
#   3. #print axioms не показывает sorryAx ни у одной теоремы.
#
# Третий пункт — единственный надёжный: `sorry` умеет приезжать через
# импорт, а grep по своим файлам этого не видит.
set -eu
cd "$(dirname "$0")/.."

echo "== 1. build =="
lake build

echo "== 2. forbidden constructs in sources =="
if grep -rnE '\b(sorry|axiom|unsafe|native_decide|partial)\b' RelationshipFix/*.lean \
     | grep -v 'Audit.lean' | grep -v '^\s*--' | grep -v 'sorryAx'; then
  echo "FAIL: forbidden construct in the kernel"
  exit 1
fi
echo "none"

echo "== 3. trusted base of every theorem =="
out=$(lake env lean RelationshipFix/Audit.lean)
echo "$out"
if echo "$out" | grep -q 'sorryAx'; then
  echo "FAIL: a theorem depends on sorryAx — it is declared, not proved"
  exit 1
fi
echo
echo "KERNEL AUDIT PASSED"
