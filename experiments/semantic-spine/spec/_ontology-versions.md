# Ontology version lineage

Файл без `rf-label`: он не описывает сущность, он объявляет рёбра между
сущностями, у которых нет собственного spec-файла. Здесь живёт единственный
факт, который нельзя приписать конкретному label'у — порядок версий онтологии.

`behavior-v0.2-candidate` помечен в самом артефакте как
`supersedes_for_future_runs: behavior-v0.1`, но это строка внутри JSON: ни один
инструмент её не проверяет и ничто не падает, если она соврёт. Здесь она
становится ребром, у которого есть обе стороны и verifier.

## Links

```rf-edge
from: "ontology:behavior-v0.2-candidate"
relation: supersedes
to: "ontology:behavior-v0.1"
note: "candidate_not_frozen; пилот v0.1 продолжает гоняться на v0.1"
```
