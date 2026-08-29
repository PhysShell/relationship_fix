namespace RelationshipFix.DataContracts.Dto;

public sealed record OntologyFileDto
{
    public required string SchemaVersion { get; init; }
    public required string OntologyVersion { get; init; }
    public required IReadOnlyList<BehaviorLabelDto> Labels { get; init; }
}

public sealed record BehaviorLabelDto
{
    public required string Id { get; init; }
    public required string CanonicalName { get; init; }
    public required string PlainLanguageNameEn { get; init; }
    public required string PlainLanguageNameRu { get; init; }
    public required string OperationalDefinition { get; init; }
    public required IReadOnlyList<string> AllowedUnits { get; init; }
    public required string Directionality { get; init; }
    public required IReadOnlyList<string> InclusionCriteria { get; init; }
    public required IReadOnlyList<string> ExclusionCriteria { get; init; }
    public required IReadOnlyList<BehaviorExampleDto> Examples { get; init; }
    public required IReadOnlyList<string> ConfusableWith { get; init; }
    public required bool EvidenceRequired { get; init; }
    public required IReadOnlyList<string> SourceFrameworks { get; init; }
    public required string Status { get; init; }
}

public sealed record BehaviorExampleDto
{
    public required string Language { get; init; }
    public required string Text { get; init; }
    public required string Unit { get; init; }
    public required string Verdict { get; init; }
    public string? Rationale { get; init; }
}
