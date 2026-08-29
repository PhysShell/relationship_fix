using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Причина воздержания — у аннотатора (человека или модели) есть право не решать,
/// и разные причины диагностируют разные проблемы онтологии/данных.
/// </summary>
[SmartEnum<string>]
public partial class AbstentionReason
{
    public static readonly AbstentionReason InsufficientContext = new("insufficient_context");
    public static readonly AbstentionReason AmbiguousBetweenLabels = new("ambiguous_between_labels");
    public static readonly AbstentionReason UnitNotApplicable = new("unit_not_applicable");
    public static readonly AbstentionReason SourceCorrupted = new("source_corrupted");
    public static readonly AbstentionReason LanguageUnsupported = new("language_unsupported");
    public static readonly AbstentionReason Other = new("other");
}
