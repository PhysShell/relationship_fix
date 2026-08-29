using NodaTime;
using RelationshipFix.DataContracts.Dto;
using Shouldly;
using Xunit;

namespace RelationshipFix.DataContracts.Tests;

/// <summary>
/// Golden wire fixtures (ADR-0002): канонические байты контракта заморожены в
/// data/contracts/. Тест падает, если сериализатор начал писать иначе ИЛИ
/// перестал читать исторический формат. Обновление — только осознанно:
/// RF_UPDATE_GOLDEN=1 перезаписывает файлы (и это diff в git, а не тихая мутация).
/// </summary>
public class GoldenContractTests
{
    public static TheoryData<string, Func<object>, Func<string, object>> Cases()
    {
        var data = new TheoryData<string, Func<object>, Func<string, object>>
        {
            {
                "source-message.v1/minimal.json",
                () => new SourceMessageDto
                {
                    SchemaVersion = "rf.source-message.v1",
                    MessageId = "m001",
                    Author = "a",
                    TimestampResolution = "exact_instant",
                    TimestampUtc = Instant.FromUtc(2026, 8, 1, 18, 0),
                    Text = "Hello.",
                },
                json => RelationshipJson.Deserialize<SourceMessageDto>(json)
            },
            {
                "source-message.v1/emoji.json",
                () => new SourceMessageDto
                {
                    SchemaVersion = "rf.source-message.v1",
                    MessageId = "m005",
                    Author = "b",
                    TimestampResolution = "local_time_unknown_zone",
                    TimestampLocal = new LocalDateTime(2026, 8, 1, 18, 5, 40),
                    Text = "ну ты дебил 😂❤️",
                },
                json => RelationshipJson.Deserialize<SourceMessageDto>(json)
            },
            {
                "source-message.v1/rtl.json",
                () => new SourceMessageDto
                {
                    SchemaVersion = "rf.source-message.v1",
                    MessageId = "m020",
                    Author = "a",
                    TimestampResolution = "local_time_with_assumed_zone",
                    TimestampLocal = new LocalDateTime(2026, 8, 2, 14, 20, 0),
                    AssumedZoneId = "Asia/Almaty",
                    Text = "שלום עולם — سلام",
                },
                json => RelationshipJson.Deserialize<SourceMessageDto>(json)
            },
            {
                "source-message.v1/combining.json",
                () => new SourceMessageDto
                {
                    SchemaVersion = "rf.source-message.v1",
                    MessageId = "m021",
                    Author = "b",
                    TimestampResolution = "exact_instant",
                    TimestampUtc = Instant.FromUtc(2026, 8, 2, 9, 13, 5),
                    Text = "café 👨‍👩‍👧‍👦",
                },
                json => RelationshipJson.Deserialize<SourceMessageDto>(json)
            },
            {
                "annotation.v1/assigned.json",
                () => new AnnotationDto
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
                            SourceTextSha256 = "2587c11593bbf9a31376aab3a1da832075a53d272ed7353f19360b8ed91233ed",
                        },
                    ],
                },
                json => RelationshipJson.Deserialize<AnnotationDto>(json)
            },
            {
                "annotation.v1/none-observed.json",
                () => new AnnotationDto
                {
                    SchemaVersion = "rf.annotation.v1",
                    MessageId = "m002",
                    Unit = "utterance",
                    AnnotatorId = "annotator-a",
                    Decision = "none_observed",
                },
                json => RelationshipJson.Deserialize<AnnotationDto>(json)
            },
            {
                "annotation.v1/abstained.json",
                () => new AnnotationDto
                {
                    SchemaVersion = "rf.annotation.v1",
                    MessageId = "m008",
                    Unit = "utterance",
                    AnnotatorId = "annotator-b",
                    Decision = "abstained",
                    AbstentionReason = "insufficient_context",
                    Note = "message too short",
                },
                json => RelationshipJson.Deserialize<AnnotationDto>(json)
            },
            {
                "finding.v1/published.json",
                () => new FindingDto
                {
                    SchemaVersion = "rf.finding.v1",
                    Status = "published",
                    Claim = "После генерализующей критики в 4 из 5 эпизодов следует защитный ответ.",
                    Evidence =
                    [
                        new EvidenceSpanDto
                        {
                            MessageId = "m001",
                            StartCodePoint = 3,
                            LengthCodePoints = 6,
                            QuotedText = "всегда",
                            SourceTextSha256 = "2587c11593bbf9a31376aab3a1da832075a53d272ed7353f19360b8ed91233ed",
                        },
                    ],
                    Counterevidence = [],
                    Confidence = new ConfidenceComponentsDto
                    {
                        RetrievalCoverage = 0.8,
                        AnnotationAgreement = 0.7,
                        SupportStrength = 0.6,
                        CounterevidenceStrength = 0.1,
                        TemporalRecurrence = 0.5,
                        MissingContextRisk = 0.3,
                    },
                },
                json => RelationshipJson.Deserialize<FindingDto>(json)
            },
            {
                "finding.v1/abstained.json",
                () => new FindingDto
                {
                    SchemaVersion = "rf.finding.v1",
                    Status = "abstained",
                    AbstentionReason = "insufficient_context",
                    Note = "Кандидат не прошёл evidence threshold: 2 подтверждения, 2 контрпримера.",
                },
                json => RelationshipJson.Deserialize<FindingDto>(json)
            },
        };
        return data;
    }

    [Theory]
    [MemberData(nameof(Cases))]
    public void Golden_fixture_matches_canonical_serialization(
        string relativePath,
        Func<object> canonicalObject,
        Func<string, object> deserialize)
    {
        var path = Path.Combine(RepoPaths.Root, "data", "contracts", relativePath);
        var canonicalJson = RelationshipJson.Serialize(canonicalObject());

        if (Environment.GetEnvironmentVariable("RF_UPDATE_GOLDEN") == "1")
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, canonicalJson + "\n");
        }

        File.Exists(path).ShouldBeTrue($"golden fixture missing: {relativePath} (run with RF_UPDATE_GOLDEN=1)");
        var stored = File.ReadAllText(path).TrimEnd('\n');

        // 1. Эмиссия заморожена: сериализатор обязан выдавать байт-в-байт то, что в git.
        canonicalJson.ShouldBe(stored);

        // 2. Чтение исторического формата: файл парсится и re-serialize даёт его же.
        RelationshipJson.Serialize(deserialize(stored)).ShouldBe(stored);
    }
}

internal static class RepoPaths
{
    public static string Root { get; } = FindRoot();

    private static string FindRoot()
    {
        var dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "RelationshipFix.slnx")))
            dir = Path.GetDirectoryName(dir);
        return dir ?? throw new InvalidOperationException("RelationshipFix.sln not found above test directory.");
    }
}
