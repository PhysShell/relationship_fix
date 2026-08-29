namespace RelationshipFix.DataContracts.Dto;

public sealed record SliceMetricsDto
{
    public required string SchemaVersion { get; init; }
    public required int MessagesTotal { get; init; }
    public required int DecisionsAssigned { get; init; }
    public required int DecisionsNoneObserved { get; init; }
    public required int DecisionsAbstained { get; init; }
    public required IReadOnlyDictionary<string, int> LabelCounts { get; init; }
    public required IReadOnlyDictionary<string, int> AbstentionReasons { get; init; }
    public required int SpansChecked { get; init; }
    public required int SpansValid { get; init; }
    public required int AnnotationValidationIssues { get; init; }
}
