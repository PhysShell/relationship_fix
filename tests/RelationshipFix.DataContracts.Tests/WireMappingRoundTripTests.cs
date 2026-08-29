using System.Collections.Immutable;
using NodaTime;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.DataContracts.Unicode;
using RelationshipFix.Domain.Evidence;
using RelationshipFix.Domain.Ontology;
using RelationshipFix.Domain.Sources;
using Shouldly;
using Xunit;

namespace RelationshipFix.DataContracts.Tests;

public class WireMappingRoundTripTests
{
    [Fact]
    public void SourceMessage_roundtrips_for_all_timestamp_resolutions()
    {
        SourceMessage[] messages =
        [
            new(MessageId.Create("m1"), ParticipantId.Create("a"),
                new SourceTimestamp.ExactInstant(Instant.FromUtc(2026, 8, 1, 18, 0)), "Привет 😂"),
            new(MessageId.Create("m2"), ParticipantId.Create("b"),
                new SourceTimestamp.LocalWithAssumedZone(new LocalDateTime(2026, 8, 2, 14, 20, 0), "Asia/Almaty"), "ok"),
            new(MessageId.Create("m3"), ParticipantId.Create("a"),
                new SourceTimestamp.LocalUnknownZone(new LocalDateTime(2026, 8, 2, 14, 32, 0)), "שלום"),
        ];

        foreach (var message in messages)
        {
            var json = RelationshipJson.Serialize(WireMapping.ToDto(message));
            var restored = WireMapping.FromDto(RelationshipJson.Deserialize<SourceMessageDto>(json));
            restored.ShouldBe(message);
        }
    }

    [Fact]
    public void Annotation_v2_roundtrips_for_all_decision_cases_on_utterance_target()
    {
        var annotator = AnnotatorId.Create("annotator-a");
        const string source = "Ты всегда 😂";
        var span = new EvidenceSpan(
            MessageId.Create("m1"),
            CodePointOffset.Create(3),
            CodePointLength.Create(6),
            "всегда",
            CodePointText.ComputeSha256(source));

        UnitAnnotation[] annotations =
        [
            new(new AnnotationTarget.Utterance(MessageId.Create("m1")), annotator,
                new AnnotationDecision.Assigned([BehaviorLabelId.Create("B.BLAME_CRITICISM")], [span])),
            new(new AnnotationTarget.Utterance(MessageId.Create("m2")), annotator,
                new AnnotationDecision.NoneObserved()),
            new(new AnnotationTarget.Utterance(MessageId.Create("m3")), annotator,
                new AnnotationDecision.Abstained(AbstentionReason.AmbiguousBetweenLabels, "humor vs contempt")),
        ];

        foreach (var annotation in annotations)
        {
            var json = RelationshipJson.Serialize(WireMapping.ToDto(annotation));
            var restored = WireMapping.FromDto(RelationshipJson.Deserialize<AnnotationV2Dto>(json));

            restored.Unit.ShouldBe(UnitOfAnalysis.Utterance);
            restored.Target.ShouldBe(annotation.Target);
            restored.Annotator.ShouldBe(annotation.Annotator);
            AssertSameDecision(restored.Decision, annotation.Decision);
        }
    }

    [Fact]
    public void Annotation_v2_roundtrips_derived_exchange_target_with_provenance()
    {
        var members = ImmutableArray.Create(
            MessageId.Create("m041"), MessageId.Create("m042"), MessageId.Create("m043"));
        var reference = DerivedUnitRef.Create(
            DerivedUnitId.Create("ex-017"), "seg-v0.1", members);

        var annotation = new UnitAnnotation(
            new AnnotationTarget.Exchange(reference),
            AnnotatorId.Create("annotator-b"),
            new AnnotationDecision.Abstained(AbstentionReason.InsufficientContext, "boundary unclear"));

        var json = RelationshipJson.Serialize(WireMapping.ToDto(annotation));
        var restored = WireMapping.FromDto(RelationshipJson.Deserialize<AnnotationV2Dto>(json));

        restored.Unit.ShouldBe(UnitOfAnalysis.Exchange);
        var restoredRef = restored.Target.Switch(
            utterance: _ => throw new InvalidOperationException("target kind changed"),
            turn: _ => throw new InvalidOperationException("target kind changed"),
            exchange: e => e.Ref,
            episode: _ => throw new InvalidOperationException("target kind changed"));

        restoredRef.UnitId.ShouldBe(reference.UnitId);
        restoredRef.SegmentationVersion.ShouldBe(reference.SegmentationVersion);
        restoredRef.MemberMessageIds.ShouldBe(reference.MemberMessageIds);
        restoredRef.MembersSha256.ShouldBe(reference.MembersSha256);
        restoredRef.MembersHashIsValid().ShouldBeTrue();
    }

    [Fact]
    public void Derived_target_with_broken_members_hash_fails_loudly()
    {
        var dto = new AnnotationTargetDto
        {
            Kind = "exchange",
            UnitId = "ex-017",
            SegmentationVersion = "seg-v0.1",
            MemberMessageIds = ["m041", "m042"],
            MembersSha256 = new string('0', 64),
        };

        var ex = Should.Throw<FormatException>(() => WireMapping.TargetFromDto(dto));
        ex.Message.ShouldContain("provenance");
    }

    [Fact]
    public void Utterance_target_with_derived_fields_fails_loudly()
    {
        var dto = new AnnotationTargetDto
        {
            Kind = "utterance",
            MessageId = "m1",
            UnitId = "ex-017",
        };

        Should.Throw<FormatException>(() => WireMapping.TargetFromDto(dto));
    }

    [Fact]
    public void Annotation_v1_migrates_to_v2_preserving_domain_meaning()
    {
        var v1 = new AnnotationDto
        {
            SchemaVersion = "rf.annotation.v1",
            MessageId = "m001",
            Unit = "utterance",
            AnnotatorId = "annotator-a",
            Decision = "assigned",
            Labels = ["B.BLAME_CRITICISM"],
            Evidence =
            [
                new EvidenceSpanDto
                {
                    MessageId = "m001",
                    StartCodePoint = 3,
                    LengthCodePoints = 6,
                    QuotedText = "всегда",
                    SourceTextSha256 = CodePointText.ComputeSha256("Ты всегда 😂"),
                },
            ],
        };

        var v2 = WireMapping.AnnotationV1ToV2(v1);
        v2.SchemaVersion.ShouldBe("rf.annotation.v2");
        v2.Target.Kind.ShouldBe("utterance");
        v2.Target.MessageId.ShouldBe("m001");

        // Legacy-путь (FromDto v1) и миграция дают одно и то же доменное значение.
        var viaLegacy = WireMapping.FromDto(v1);
        var viaMigration = WireMapping.FromDto(v2);
        viaMigration.Target.ShouldBe(viaLegacy.Target);
        viaMigration.Annotator.ShouldBe(viaLegacy.Annotator);
        AssertSameDecision(viaMigration.Decision, viaLegacy.Decision);
    }

    [Fact]
    public void Unknown_discriminators_fail_loudly()
    {
        var badDecision = """{"schema_version":"rf.annotation.v2","target":{"kind":"utterance","message_id":"m1"},"annotator_id":"x","decision":"vibed"}""";
        Should.Throw<FormatException>(() =>
            WireMapping.FromDto(RelationshipJson.Deserialize<AnnotationV2Dto>(badDecision)));

        var badKind = new AnnotationTargetDto { Kind = "vibe-cluster", MessageId = "m1" };
        Should.Throw<FormatException>(() => WireMapping.TargetFromDto(badKind));
    }

    private static void AssertSameDecision(AnnotationDecision actual, AnnotationDecision expected) =>
        actual.Switch(
            assigned: a => expected.Switch(
                assigned: e =>
                {
                    a.Labels.ShouldBe(e.Labels);
                    a.Evidence.ShouldBe(e.Evidence);
                },
                noneObserved: _ => throw new InvalidOperationException("decision case changed"),
                abstained: _ => throw new InvalidOperationException("decision case changed")),
            noneObserved: _ => expected.ShouldBeOfType<AnnotationDecision.NoneObserved>(),
            abstained: a => expected.Switch(
                assigned: _ => throw new InvalidOperationException("decision case changed"),
                noneObserved: _ => throw new InvalidOperationException("decision case changed"),
                abstained: e =>
                {
                    a.Reason.ShouldBe(e.Reason);
                    a.Note.ShouldBe(e.Note);
                }));
}
