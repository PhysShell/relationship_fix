Слои разметчиков Pilot B: `annotator-N-relation.jsonl` (`rf.primitives-response.v1`) и
`annotator-N-segmentation.jsonl` (`rf.primitives-boundary-response.v1`), N = 1..3.

Пусто до выдачи. После заморозки всех слоёв не редактируются.

`metrics.primitives report` отказывается строить отчёт, пока не сдано минимум два слоя.
