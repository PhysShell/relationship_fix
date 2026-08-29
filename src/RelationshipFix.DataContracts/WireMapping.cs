using System.Collections.Immutable;
using NodaTime.Text;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.Domain.Evidence;
using RelationshipFix.Domain.Ontology;
using RelationshipFix.Domain.Sources;

namespace RelationshipFix.DataContracts;

/// <summary>
/// Явный маппинг domain ↔ wire. Никаких nameof/ToString по типам —
/// каждое соответствие прописано руками и защищено golden fixtures.
/// </summary>
public static class WireMapping
{
    // --- SourceMessage ---

    public static SourceMessageDto ToDto(SourceMessage message) =>
        message.Timestamp.Switch(
            exactInstant: t => new SourceMessageDto
            {
                SchemaVersion = WireSchema.SourceMessageV1,
                MessageId = message.Id,
                Author = message.Author,
                TimestampResolution = TimestampResolutionWire.ExactInstant,
                TimestampUtc = t.Value,
                Text = message.Text,
            },
            localWithAssumedZone: t => new SourceMessageDto
            {
                SchemaVersion = WireSchema.SourceMessageV1,
                MessageId = message.Id,
                Author = message.Author,
                TimestampResolution = TimestampResolutionWire.LocalWithAssumedZone,
                TimestampLocal = t.Value,
                AssumedZoneId = t.ZoneId,
                Text = message.Text,
            },
            localUnknownZone: t => new SourceMessageDto
            {
                SchemaVersion = WireSchema.SourceMessageV1,
                MessageId = message.Id,
                Author = message.Author,
                TimestampResolution = TimestampResolutionWire.LocalUnknownZone,
                TimestampLocal = t.Value,
                Text = message.Text,
            });

    public static SourceMessage FromDto(SourceMessageDto dto)
    {
        RequireSchema(dto.SchemaVersion, WireSchema.SourceMessageV1);

        SourceTimestamp timestamp = dto.TimestampResolution switch
        {
            TimestampResolutionWire.ExactInstant => new SourceTimestamp.ExactInstant(
                dto.TimestampUtc ?? throw Missing("timestamp_utc")),
            TimestampResolutionWire.LocalWithAssumedZone => new SourceTimestamp.LocalWithAssumedZone(
                dto.TimestampLocal ?? throw Missing("timestamp_local"),
                dto.AssumedZoneId ?? throw Missing("assumed_zone_id")),
            TimestampResolutionWire.LocalUnknownZone => new SourceTimestamp.LocalUnknownZone(
                dto.TimestampLocal ?? throw Missing("timestamp_local")),
            var other => throw new FormatException($"Unknown timestamp_resolution '{other}'."),
        };

        return new SourceMessage(
            MessageId.Create(dto.MessageId),
            ParticipantId.Create(dto.Author),
            timestamp,
            dto.Text);
    }

    // --- EvidenceSpan ---

    public static EvidenceSpanDto ToDto(EvidenceSpan span) => new()
    {
        MessageId = span.MessageId,
        StartCodePoint = span.StartCodePoint,
        LengthCodePoints = span.LengthCodePoints,
        QuotedText = span.QuotedText,
        SourceTextSha256 = span.SourceTextSha256,
    };

    public static EvidenceSpan FromDto(EvidenceSpanDto dto) => new(
        MessageId.Create(dto.MessageId),
        CodePointOffset.Create(dto.StartCodePoint),
        CodePointLength.Create(dto.LengthCodePoints),
        dto.QuotedText,
        Sha256Hex.Create(dto.SourceTextSha256));

    // --- UnitAnnotation ---

    public static AnnotationDto ToDto(UnitAnnotation annotation) =>
        annotation.Decision.Switch(
            assigned: a => new AnnotationDto
            {
                SchemaVersion = WireSchema.AnnotationV1,
                MessageId = annotation.MessageId,
                Unit = annotation.Unit.Key,
                AnnotatorId = annotation.Annotator,
                Decision = AnnotationDecisionWire.Assigned,
                Labels = a.Labels.Select(l => (string)l).ToArray(),
                Evidence = a.Evidence.Select(ToDto).ToArray(),
            },
            noneObserved: _ => new AnnotationDto
            {
                SchemaVersion = WireSchema.AnnotationV1,
                MessageId = annotation.MessageId,
                Unit = annotation.Unit.Key,
                AnnotatorId = annotation.Annotator,
                Decision = AnnotationDecisionWire.NoneObserved,
            },
            abstained: a => new AnnotationDto
            {
                SchemaVersion = WireSchema.AnnotationV1,
                MessageId = annotation.MessageId,
                Unit = annotation.Unit.Key,
                AnnotatorId = annotation.Annotator,
                Decision = AnnotationDecisionWire.Abstained,
                AbstentionReason = a.Reason.Key,
                Note = a.Note,
            });

    public static UnitAnnotation FromDto(AnnotationDto dto)
    {
        RequireSchema(dto.SchemaVersion, WireSchema.AnnotationV1);

        AnnotationDecision decision = dto.Decision switch
        {
            AnnotationDecisionWire.Assigned => new AnnotationDecision.Assigned(
                (dto.Labels ?? throw Missing("labels"))
                    .Select(BehaviorLabelId.Create).ToImmutableArray(),
                (dto.Evidence ?? []).Select(FromDto).ToImmutableArray()),
            AnnotationDecisionWire.NoneObserved => new AnnotationDecision.NoneObserved(),
            AnnotationDecisionWire.Abstained => new AnnotationDecision.Abstained(
                AbstentionReason.Get(dto.AbstentionReason ?? throw Missing("abstention_reason")),
                dto.Note),
            var other => throw new FormatException($"Unknown annotation decision '{other}'."),
        };

        return new UnitAnnotation(
            MessageId.Create(dto.MessageId),
            UnitOfAnalysis.Get(dto.Unit),
            AnnotatorId.Create(dto.AnnotatorId),
            decision);
    }

    // --- Ontology (wire → domain; онтология авторится как файл, не сериализуется обратно) ---

    public static BehaviorOntology OntologyFromDto(OntologyFileDto dto)
    {
        RequireSchema(dto.SchemaVersion, WireSchema.OntologyV1);

        var labels = dto.Labels.Select(l => new BehaviorLabelDefinition(
            BehaviorLabelId.Create(l.Id),
            l.CanonicalName,
            l.PlainLanguageNameEn,
            l.PlainLanguageNameRu,
            l.OperationalDefinition,
            [.. l.AllowedUnits.Select(u => UnitOfAnalysis.Get(u))],
            Directionality.Get(l.Directionality),
            [.. l.InclusionCriteria],
            [.. l.ExclusionCriteria],
            [.. l.Examples.Select(e => new BehaviorExample(
                e.Language, e.Text, UnitOfAnalysis.Get(e.Unit), ExampleVerdict.Get(e.Verdict), e.Rationale))],
            [.. l.ConfusableWith.Select(BehaviorLabelId.Create)],
            l.EvidenceRequired,
            [.. l.SourceFrameworks],
            LabelStatus.Get(l.Status))).ToImmutableArray();

        return new BehaviorOntology(dto.OntologyVersion, labels);
    }

    public static InstantPattern InstantWirePattern => InstantPattern.ExtendedIso;

    private static FormatException Missing(string field) =>
        new($"Required wire field '{field}' is missing.");

    private static void RequireSchema(string actual, string expected)
    {
        if (!string.Equals(actual, expected, StringComparison.Ordinal))
            throw new FormatException($"Expected schema '{expected}', got '{actual}'.");
    }
}
