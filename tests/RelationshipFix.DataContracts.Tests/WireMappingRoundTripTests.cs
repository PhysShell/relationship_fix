using System.Collections.Immutable;
using NodaTime;
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
            var restored = WireMapping.FromDto(
                RelationshipJson.Deserialize<DataContracts.Dto.SourceMessageDto>(json));
            restored.ShouldBe(message);
        }
    }

    [Fact]
    public void Annotation_roundtrips_for_all_decision_cases()
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
            new(MessageId.Create("m1"), UnitOfAnalysis.Utterance, annotator,
                new AnnotationDecision.Assigned(
                    [BehaviorLabelId.Create("B.BLAME_CRITICISM")],
                    [span])),
            new(MessageId.Create("m2"), UnitOfAnalysis.Utterance, annotator,
                new AnnotationDecision.NoneObserved()),
            new(MessageId.Create("m3"), UnitOfAnalysis.Utterance, annotator,
                new AnnotationDecision.Abstained(AbstentionReason.AmbiguousBetweenLabels, "humor vs contempt")),
        ];

        foreach (var annotation in annotations)
        {
            var json = RelationshipJson.Serialize(WireMapping.ToDto(annotation));
            var restored = WireMapping.FromDto(
                RelationshipJson.Deserialize<DataContracts.Dto.AnnotationDto>(json));

            restored.MessageId.ShouldBe(annotation.MessageId);
            restored.Unit.ShouldBe(annotation.Unit);
            restored.Annotator.ShouldBe(annotation.Annotator);
            restored.Decision.Switch(
                assigned: a => annotation.Decision.Switch(
                    assigned: expected =>
                    {
                        a.Labels.ShouldBe(expected.Labels);
                        a.Evidence.ShouldBe(expected.Evidence);
                    },
                    noneObserved: _ => throw new InvalidOperationException("decision case changed"),
                    abstained: _ => throw new InvalidOperationException("decision case changed")),
                noneObserved: _ => annotation.Decision.ShouldBeOfType<AnnotationDecision.NoneObserved>(),
                abstained: a => annotation.Decision.Switch(
                    assigned: _ => throw new InvalidOperationException("decision case changed"),
                    noneObserved: _ => throw new InvalidOperationException("decision case changed"),
                    abstained: expected =>
                    {
                        a.Reason.ShouldBe(expected.Reason);
                        a.Note.ShouldBe(expected.Note);
                    }));
        }
    }

    [Fact]
    public void Unknown_discriminator_fails_loudly()
    {
        var json = """{"schema_version":"rf.annotation.v1","message_id":"m1","unit":"utterance","annotator_id":"x","decision":"vibed"}""";
        Should.Throw<FormatException>(() =>
            WireMapping.FromDto(RelationshipJson.Deserialize<DataContracts.Dto.AnnotationDto>(json)));
    }
}
