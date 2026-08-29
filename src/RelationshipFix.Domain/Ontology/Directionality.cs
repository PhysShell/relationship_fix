using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Семантическая цель поведения на уровне определения label:
/// other-directed (blame — про другого), self-directed (self-disclosure — про себя),
/// interaction-directed (repair, withdrawal, topic shift — действие адресовано самому
/// взаимодействию/напряжению, а не одному из участников). Структуру единицы
/// (utterance/turn/exchange) описывает отдельная ось — unit_of_analysis.
/// </summary>
[SmartEnum<string>]
public partial class Directionality
{
    public static readonly Directionality OtherDirected = new("other_directed");
    public static readonly Directionality SelfDirected = new("self_directed");
    public static readonly Directionality InteractionDirected = new("interaction_directed");
}
