using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Направленность поведения на уровне определения label:
/// other-directed (blame — про другого), self-directed (taking responsibility — про себя),
/// dyadic (свойство обмена, а не одного участника).
/// </summary>
[SmartEnum<string>]
public partial class Directionality
{
    public static readonly Directionality OtherDirected = new("other_directed");
    public static readonly Directionality SelfDirected = new("self_directed");
    public static readonly Directionality Dyadic = new("dyadic");
}
