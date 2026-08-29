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

/// <summary>
/// Аннотация одной единицы анализа. Единица определяется целью (AnnotationTarget):
/// kind цели и есть unit — отдельного поля нет, рассинхрон невозможен по построению.
/// </summary>
public sealed record UnitAnnotation(
    AnnotationTarget Target,
    AnnotatorId Annotator,
    AnnotationDecision Decision)
{
    public UnitOfAnalysis Unit => Target.Switch(
        utterance: _ => UnitOfAnalysis.Utterance,
        turn: _ => UnitOfAnalysis.Turn,
        exchange: _ => UnitOfAnalysis.Exchange,
        episode: _ => UnitOfAnalysis.Episode);
}
