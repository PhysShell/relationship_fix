using System.Collections.Immutable;
using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

[SmartEnum<string>]
public partial class ExampleVerdict
{
    public static readonly ExampleVerdict Positive = new("positive");
    public static readonly ExampleVerdict Negative = new("negative");
    public static readonly ExampleVerdict Ambiguous = new("ambiguous");
}

/// <summary>Пример к label. Примеры обязаны существовать на обоих рабочих языках (ru/en).</summary>
public sealed record BehaviorExample(
    string Language,
    string Text,
    UnitOfAnalysis Unit,
    ExampleVerdict Verdict,
    string? Rationale);

/// <summary>
/// Определение behavior label — machine-readable constraint, а не только документация:
/// annotation validator отвергает label на недопустимой единице анализа до сохранения.
/// </summary>
public sealed record BehaviorLabelDefinition(
    BehaviorLabelId Id,
    string CanonicalName,
    string PlainLanguageNameEn,
    string PlainLanguageNameRu,
    string OperationalDefinition,
    ImmutableArray<UnitOfAnalysis> AllowedUnits,
    Directionality Directionality,
    ImmutableArray<string> InclusionCriteria,
    ImmutableArray<string> ExclusionCriteria,
    ImmutableArray<BehaviorExample> Examples,
    ImmutableArray<BehaviorLabelId> ConfusableWith,
    bool EvidenceRequired,
    ImmutableArray<string> SourceFrameworks,
    LabelStatus Status)
{
    public bool AllowsUnit(UnitOfAnalysis unit) => AllowedUnits.Contains(unit);
}

/// <summary>Версионированная онтология. Изменение состава/определений = новая версия, не правка старой.</summary>
public sealed record BehaviorOntology(
    string Version,
    ImmutableArray<BehaviorLabelDefinition> Labels)
{
    public BehaviorLabelDefinition? Find(BehaviorLabelId id) =>
        Labels.FirstOrDefault(l => l.Id == id);
}
