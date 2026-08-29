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

    // --- UnitAnnotation: пишем rf.annotation.v2; v1 читается и мигрируется (заморожен) ---

    public static AnnotationV2Dto ToDto(UnitAnnotation annotation)
    {
        var (decision, labels, evidence, reason, note) = annotation.Decision.Switch<(string, IReadOnlyList<string>?, IReadOnlyList<EvidenceSpanDto>?, string?, string?)>(
            assigned: a => (
                AnnotationDecisionWire.Assigned,
                a.Labels.Select(l => (string)l).ToArray(),
                a.Evidence.Select(ToDto).ToArray(),
                null,
                null),
            noneObserved: _ => (AnnotationDecisionWire.NoneObserved, null, null, null, null),
            abstained: a => (AnnotationDecisionWire.Abstained, null, null, a.Reason.Key, a.Note));

        return new AnnotationV2Dto
        {
            SchemaVersion = WireSchema.AnnotationV2,
            Target = ToDto(annotation.Target),
            AnnotatorId = annotation.Annotator,
            Decision = decision,
            Labels = labels,
            Evidence = evidence,
            AbstentionReason = reason,
            Note = note,
        };
    }

    public static AnnotationTargetDto ToDto(AnnotationTarget target) =>
        target.Switch(
            utterance: u => new AnnotationTargetDto
            {
                Kind = TargetKindWire.Utterance,
                MessageId = u.MessageId,
            },
            turn: t => DerivedTargetDto(TargetKindWire.Turn, t.Ref),
            exchange: e => DerivedTargetDto(TargetKindWire.Exchange, e.Ref),
            episode: e => DerivedTargetDto(TargetKindWire.Episode, e.Ref));

    private static AnnotationTargetDto DerivedTargetDto(string kind, DerivedUnitRef reference) => new()
    {
        Kind = kind,
        UnitId = reference.UnitId,
        SegmentationVersion = reference.SegmentationVersion,
        MemberMessageIds = reference.MemberMessageIds.Select(m => (string)m).ToArray(),
        MembersSha256 = reference.MembersSha256,
    };

    public static UnitAnnotation FromDto(AnnotationV2Dto dto)
    {
        RequireSchema(dto.SchemaVersion, WireSchema.AnnotationV2);
        return new UnitAnnotation(
            TargetFromDto(dto.Target),
            AnnotatorId.Create(dto.AnnotatorId),
            DecisionFromWire(dto.Decision, dto.Labels, dto.Evidence, dto.AbstentionReason, dto.Note));
    }

    public static AnnotationTarget TargetFromDto(AnnotationTargetDto dto)
    {
        switch (dto.Kind)
        {
            case TargetKindWire.Utterance:
                if (dto.UnitId is not null || dto.SegmentationVersion is not null ||
                    dto.MemberMessageIds is not null || dto.MembersSha256 is not null)
                    throw new FormatException("Utterance target must not carry derived-unit fields.");
                return new AnnotationTarget.Utterance(
                    MessageId.Create(dto.MessageId ?? throw Missing("target.message_id")));

            case TargetKindWire.Turn:
            case TargetKindWire.Exchange:
            case TargetKindWire.Episode:
                if (dto.MessageId is not null)
                    throw new FormatException($"'{dto.Kind}' target must not carry message_id.");
                var reference = new DerivedUnitRef(
                    DerivedUnitId.Create(dto.UnitId ?? throw Missing("target.unit_id")),
                    dto.SegmentationVersion ?? throw Missing("target.segmentation_version"),
                    (dto.MemberMessageIds ?? throw Missing("target.member_message_ids"))
                        .Select(MessageId.Create).ToImmutableArray(),
                    Sha256Hex.Create(dto.MembersSha256 ?? throw Missing("target.members_sha256")));
                if (!reference.MembersHashIsValid())
                    throw new FormatException(
                        $"Derived unit '{dto.UnitId}': members_sha256 does not match member_message_ids — " +
                        "provenance is broken or segmentation changed under the same unit id.");
                return dto.Kind switch
                {
                    TargetKindWire.Turn => new AnnotationTarget.Turn(reference),
                    TargetKindWire.Exchange => new AnnotationTarget.Exchange(reference),
                    _ => new AnnotationTarget.Episode(reference),
                };

            default:
                throw new FormatException($"Unknown target kind '{dto.Kind}'.");
        }
    }

    /// <summary>Legacy-чтение исторического rf.annotation.v1 (utterance-only по построению).</summary>
    public static UnitAnnotation FromDto(AnnotationDto dto) => FromDto(AnnotationV1ToV2(dto));

    /// <summary>Миграция v1 → v2 (ADR-0002 §4): message_id → target{kind: utterance}.</summary>
    public static AnnotationV2Dto AnnotationV1ToV2(AnnotationDto dto)
    {
        RequireSchema(dto.SchemaVersion, WireSchema.AnnotationV1);
        if (dto.Unit != TargetKindWire.Utterance)
            throw new FormatException(
                $"rf.annotation.v1 is utterance-only by construction; got unit '{dto.Unit}'.");

        return new AnnotationV2Dto
        {
            SchemaVersion = WireSchema.AnnotationV2,
            Target = new AnnotationTargetDto { Kind = TargetKindWire.Utterance, MessageId = dto.MessageId },
            AnnotatorId = dto.AnnotatorId,
            Decision = dto.Decision,
            Labels = dto.Labels,
            Evidence = dto.Evidence,
            AbstentionReason = dto.AbstentionReason,
            Note = dto.Note,
        };
    }

    private static AnnotationDecision DecisionFromWire(
        string decision,
        IReadOnlyList<string>? labels,
        IReadOnlyList<EvidenceSpanDto>? evidence,
        string? abstentionReason,
        string? note) => decision switch
    {
        AnnotationDecisionWire.Assigned => new AnnotationDecision.Assigned(
            (labels ?? throw Missing("labels")).Select(BehaviorLabelId.Create).ToImmutableArray(),
            (evidence ?? []).Select(FromDto).ToImmutableArray()),
        AnnotationDecisionWire.NoneObserved => new AnnotationDecision.NoneObserved(),
        AnnotationDecisionWire.Abstained => new AnnotationDecision.Abstained(
            AbstentionReason.Get(abstentionReason ?? throw Missing("abstention_reason")),
            note),
        var other => throw new FormatException($"Unknown annotation decision '{other}'."),
    };

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
