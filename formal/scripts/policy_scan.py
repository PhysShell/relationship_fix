"""Запрещённые конструкции — в КОДЕ, а не в комментариях.

Наивный grep спотыкается о собственные пояснения: в этом ядре слова `sorry`,
`axiom` и `native_decide` встречаются в комментариях десятки раз, и ровно
затем, чтобы объяснить, почему их нельзя. Поэтому комментарии сначала
вырезаются, а потом сканируется остаток.

Это POLICY CHECK, а не proof check. Настоящую гарантию даёт доверенная база
из `#print axioms`, прибитая `#guard_msgs` в FinalCheck: `sorry` умеет
приезжать импортом, и никакой grep по своим файлам этого не увидит.
"""
import pathlib
import re
import sys

FORBIDDEN = (
    (r"\bsorry\b", "sorry"),
    (r"\badmit\b", "admit"),
    (r"^\s*axiom\b", "axiom"),
    (r"\bunsafe\b", "unsafe"),
    (r"\bpartial\b", "partial"),
    (r"\bnative_decide\b", "native_decide"),
    (r"@\[\s*implemented_by", "implemented_by"),
    (r"@\[\s*extern", "extern"),
)

#: Challenge — ДОВЕРЕННЫЙ файл задания, и `sorry` там означает дыру в
#: ВОПРОСЕ, а не в доказательстве. Он исключён из этого скана намеренно и
#: проверяется иначе: FinalCheck требует, чтобы его теоремы зависели от
#: `sorryAx`, а отдельный гейт запрещает импортировать его деревом
#: доказательств.
EXEMPT = {"RelationshipFix/Verification/Challenge.lean"}


def strip_comments(text: str) -> str:
    out, depth, index = [], 0, 0
    while index < len(text):
        if text.startswith("/-", index):
            depth += 1
            index += 2
        elif text.startswith("-/", index) and depth:
            depth -= 1
            index += 2
        elif depth:
            out.append("\n" if text[index] == "\n" else " ")
            index += 1
        elif text.startswith("--", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        else:
            out.append(text[index])
            index += 1
    return "".join(out)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted(root.rglob("*.lean")):
        relative = path.relative_to(root).as_posix()
        if relative in EXEMPT or ".lake" in relative:
            continue
        code = strip_comments(path.read_text(encoding="utf-8"))
        for number, line in enumerate(code.splitlines(), 1):
            for pattern, label in FORBIDDEN:
                if re.search(pattern, line):
                    offenders.append(f"{relative}:{number}: {label} -> {line.strip()}")
    for row in offenders:
        print(f"  {row}")
    if offenders:
        print("FAIL: forbidden construct in the kernel")
        return 1
    print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
