namespace RelationshipFix.DataContracts;

// ADR-0002: дискриминаторы и schema id — замороженные строки контракта.
// Они НИКОГДА не выводятся из имён C#-типов: rename-refactor не имеет права
// менять старые JSONL. Маппинг domain <-> wire всегда явный.

public static class WireSchema
{
    public const string SourceMessageV1 = "rf.source-message.v1";
    public const string AnnotationV1 = "rf.annotation.v1";
    public const string FindingV1 = "rf.finding.v1";
    public const string RunManifestV1 = "rf.run-manifest.v1";
    public const string OntologyV1 = "rf.ontology.v1";
    public const string SliceMetricsV1 = "rf.slice-metrics.v1";
}

public static class AnnotationDecisionWire
{
    public const string Assigned = "assigned";
    public const string NoneObserved = "none_observed";
    public const string Abstained = "abstained";
}

public static class FindingStatusWire
{
    public const string Published = "published";
    public const string Abstained = "abstained";
}

public static class TimestampResolutionWire
{
    public const string ExactInstant = "exact_instant";
    public const string LocalWithAssumedZone = "local_time_with_assumed_zone";
    public const string LocalUnknownZone = "local_time_unknown_zone";
}
