using System.Collections.Immutable;
using RelationshipFix.DataContracts.Unicode;
using RelationshipFix.Domain.Evidence;
using RelationshipFix.Domain.Ontology;
using RelationshipFix.Domain.Sources;

namespace RelationshipFix.Evaluation.Slice;

/// <summary>
/// Детерминированный keyword-стаб вместо модели: его задача — прогнать данные
/// через ВЕСЬ контракт (labels, evidence spans в code points, none_observed,
/// abstention), а не быть правдоподобной психологией. Заведомо туп; заменяется
/// LlmAnnotator'ом за тем же интерфейсом.
/// </summary>
public sealed class RuleStubAnnotator : ISliceAnnotator
{
    public const string AnnotatorIdValue = "rule-stub-v0";

    private static readonly (string Keyword, string LabelId)[] Rules =
    [
        ("всегда", "B.BLAME_CRITICISM"),
        ("никогда", "B.BLAME_CRITICISM"),
        ("always", "B.BLAME_CRITICISM"),
        ("never", "B.BLAME_CRITICISM"),
        ("прости", "B.REPAIR_ATTEMPT"),
        ("извини", "B.REPAIR_ATTEMPT"),
        ("sorry", "B.REPAIR_ATTEMPT"),
        ("понимаю", "B.VALIDATION"),
        ("understand", "B.VALIDATION"),
    ];

    public AnnotatorId Id => AnnotatorId.Create(AnnotatorIdValue);

    public UnitAnnotation Annotate(SourceMessage message)
    {
        if (CodePointText.CountCodePoints(message.Text) < 2)
        {
            return new UnitAnnotation(
                new AnnotationTarget.Utterance(message.Id),
                Id,
                new AnnotationDecision.Abstained(
                    AbstentionReason.InsufficientContext,
                    "message too short for utterance-level coding"));
        }

        var labels = ImmutableArray.CreateBuilder<BehaviorLabelId>();
        var evidence = ImmutableArray.CreateBuilder<EvidenceSpan>();
        var sourceHash = CodePointText.ComputeSha256(message.Text);

        foreach (var (keyword, labelId) in Rules)
        {
            var utf16Index = message.Text.IndexOf(keyword, StringComparison.OrdinalIgnoreCase);
            if (utf16Index < 0)
                continue;

            var behaviorLabel = BehaviorLabelId.Create(labelId);
            if (!labels.Contains(behaviorLabel))
                labels.Add(behaviorLabel);

            // Матчим по исходному тексту (не lowercased-копии!) и переводим
            // UTF-16 индекс в code-point координаты.
            var matched = message.Text.Substring(utf16Index, keyword.Length);
            evidence.Add(new EvidenceSpan(
                message.Id,
                CodePointOffset.Create(CodePointText.Utf16IndexToCodePointIndex(message.Text, utf16Index)),
                CodePointLength.Create(CodePointText.CountCodePoints(matched)),
                matched,
                sourceHash));
        }

        AnnotationDecision decision = labels.Count > 0
            ? new AnnotationDecision.Assigned(labels.ToImmutable(), evidence.ToImmutable())
            : new AnnotationDecision.NoneObserved();

        return new UnitAnnotation(new AnnotationTarget.Utterance(message.Id), Id, decision);
    }
}

public interface ISliceAnnotator
{
    AnnotatorId Id { get; }

    UnitAnnotation Annotate(SourceMessage message);
}
