namespace RelationshipFix.DataContracts.Dto;

/// <summary>
/// Цель аннотации в rf.annotation.v2. Форма зависит от kind:
/// utterance → только message_id; turn/exchange/episode → полный derived-unit
/// provenance (unit_id + segmentation_version + member_message_ids + members_sha256).
/// Смешанные формы отвергаются маппингом громко.
/// </summary>
public sealed record AnnotationTargetDto
{
    public required string Kind { get; init; }
    public string? MessageId { get; init; }
    public string? UnitId { get; init; }
    public string? SegmentationVersion { get; init; }
    public IReadOnlyList<string>? MemberMessageIds { get; init; }
    public string? MembersSha256 { get; init; }
}

public sealed record AnnotationV2Dto
{
    public required string SchemaVersion { get; init; }
    public required AnnotationTargetDto Target { get; init; }
    public required string AnnotatorId { get; init; }
    public required string Decision { get; init; }
    public IReadOnlyList<string>? Labels { get; init; }
    public IReadOnlyList<EvidenceSpanDto>? Evidence { get; init; }
    public string? AbstentionReason { get; init; }
    public string? Note { get; init; }
}
