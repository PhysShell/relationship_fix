using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Единица анализа, к которой применим behavior label. Часть контракта онтологии:
/// у каждого label задан непустой набор допустимых единиц (например, withdrawal
/// в тексте наблюдаем только на уровне turn/exchange, не отдельной реплики).
/// </summary>
[SmartEnum<string>]
public partial class UnitOfAnalysis
{
    public static readonly UnitOfAnalysis Utterance = new("utterance");
    public static readonly UnitOfAnalysis Turn = new("turn");
    public static readonly UnitOfAnalysis Exchange = new("exchange");
    public static readonly UnitOfAnalysis Episode = new("episode");
}
