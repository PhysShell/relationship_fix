using System.Collections.Immutable;
using RelationshipFix.Domain.Evidence;
using RelationshipFix.Domain.Ontology;
using Thinktecture;

namespace RelationshipFix.Domain.Findings;

/// <summary>
/// Компоненты калибруемой уверенности (evaluation contract §3). Итоговый порог
/// публикации выводится из этих наблюдаемых величин, а не из самоотчёта LLM.
/// </summary>
public sealed record ConfidenceComponents(
    double RetrievalCoverage,
    double AnnotationAgreement,
    double SupportStrength,
    double CounterevidenceStrength,
    double TemporalRecurrence,
    double MissingContextRisk);

public sealed record PublishedFinding(
    string Claim,
    ImmutableArray<EvidenceSpan> Evidence,
    ImmutableArray<EvidenceSpan> Counterevidence,
    ConfidenceComponents Confidence);

/// <summary>
/// Published | Abstained — ноль опубликованных findings является успешным
/// калиброванным исходом (инвариант №9, evaluation contract §1).
/// </summary>
[Union]
public partial record FindingDecision
{
    public sealed record Published(PublishedFinding Finding) : FindingDecision;

    public sealed record Abstained(AbstentionReason Reason, string? Note) : FindingDecision;
}
