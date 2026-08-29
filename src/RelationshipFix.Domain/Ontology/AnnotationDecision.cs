using System.Collections.Immutable;
using RelationshipFix.Domain.Evidence;
using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Решение аннотатора по одной единице анализа. Три исхода принципиально различны:
/// Assigned — наблюдаемое поведение найдено (≥1 label, evidence обязателен для
/// labels с EvidenceRequired); NoneObserved — единица рассмотрена и не содержит
/// ни одного поведения из онтологии (самый частый и совершенно валидный исход);
/// Abstained — аннотатор не может решить, с причиной.
/// </summary>
[Union]
public partial record AnnotationDecision
{
    public sealed record Assigned(
        ImmutableArray<BehaviorLabelId> Labels,
        ImmutableArray<EvidenceSpan> Evidence) : AnnotationDecision;

    public sealed record NoneObserved : AnnotationDecision;

    public sealed record Abstained(AbstentionReason Reason, string? Note) : AnnotationDecision;
}

/// <summary>Аннотация одной единицы анализа (v0: единица = utterance, ключ = MessageId).</summary>
public sealed record UnitAnnotation(
    MessageId MessageId,
    UnitOfAnalysis Unit,
    AnnotatorId Annotator,
    AnnotationDecision Decision);
