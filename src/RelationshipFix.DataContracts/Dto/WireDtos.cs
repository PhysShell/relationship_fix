using NodaTime;

namespace RelationshipFix.DataContracts.Dto;

// Wire DTO: только примитивы/NodaTime, никакой доменной логики.
// Порядок свойств = порядок объявления = канонический порядок сериализации.

public sealed record SourceMessageDto
{
    public required string SchemaVersion { get; init; }
    public required string MessageId { get; init; }
    public required string Author { get; init; }
    public required string TimestampResolution { get; init; }
    public Instant? TimestampUtc { get; init; }
    public LocalDateTime? TimestampLocal { get; init; }
    public string? AssumedZoneId { get; init; }
    public required string Text { get; init; }
}

public sealed record EvidenceSpanDto
{
    public required string MessageId { get; init; }
    public required int StartCodePoint { get; init; }
    public required int LengthCodePoints { get; init; }
    public required string QuotedText { get; init; }
    public required string SourceTextSha256 { get; init; }
}

public sealed record AnnotationDto
{
    public required string SchemaVersion { get; init; }
    public required string MessageId { get; init; }
    public required string Unit { get; init; }
    public required string AnnotatorId { get; init; }
    public required string Decision { get; init; }
    public IReadOnlyList<string>? Labels { get; init; }
    public IReadOnlyList<EvidenceSpanDto>? Evidence { get; init; }
    public string? AbstentionReason { get; init; }
    public string? Note { get; init; }
}

public sealed record ConfidenceComponentsDto
{
    public required double RetrievalCoverage { get; init; }
    public required double AnnotationAgreement { get; init; }
    public required double SupportStrength { get; init; }
    public required double CounterevidenceStrength { get; init; }
    public required double TemporalRecurrence { get; init; }
    public required double MissingContextRisk { get; init; }
}

public sealed record FindingDto
{
    public required string SchemaVersion { get; init; }
    public required string Status { get; init; }
    public string? Claim { get; init; }
    public IReadOnlyList<EvidenceSpanDto>? Evidence { get; init; }
    public IReadOnlyList<EvidenceSpanDto>? Counterevidence { get; init; }
    public ConfidenceComponentsDto? Confidence { get; init; }
    public string? AbstentionReason { get; init; }
    public string? Note { get; init; }
}

public sealed record GitInfoDto
{
    public required string Commit { get; init; }
    public required bool Dirty { get; init; }
}

public sealed record ArtifactRefDto
{
    public required string Id { get; init; }
    public required string Sha256 { get; init; }
}

public sealed record ModelRefDto
{
    public required string Provider { get; init; }
    public required string ModelId { get; init; }
    public IReadOnlyDictionary<string, string>? InferenceParams { get; init; }
}

public sealed record RunManifestDto
{
    public required string SchemaVersion { get; init; }
    public required string RunId { get; init; }
    public required Instant StartedAt { get; init; }
    public required GitInfoDto Git { get; init; }
    public required ArtifactRefDto Ontology { get; init; }
    public required ArtifactRefDto Dataset { get; init; }
    public required string AnnotatorId { get; init; }
    public ModelRefDto? Model { get; init; }
}
