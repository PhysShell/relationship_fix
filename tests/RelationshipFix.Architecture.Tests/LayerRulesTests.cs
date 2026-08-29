using ArchUnitNET.Domain;
using ArchUnitNET.Loader;
using ArchUnitNET.xUnitV3;
using Xunit;
using static ArchUnitNET.Fluent.ArchRuleDefinition;

namespace RelationshipFix.Architecture.Tests;

/// <summary>Межслойные правила на уровне типов (ADR-0001), поверх reflection-фактов.</summary>
public class LayerRulesTests
{
    private static readonly ArchUnitNET.Domain.Architecture Architecture = new ArchLoader()
        .LoadAssemblies(
            System.Reflection.Assembly.Load("RelationshipFix.Domain"),
            System.Reflection.Assembly.Load("RelationshipFix.DataContracts"),
            System.Reflection.Assembly.Load("RelationshipFix.Evaluation"),
            System.Reflection.Assembly.Load("RelationshipFix.AI.Abstractions"),
            System.Reflection.Assembly.Load("RelationshipFix.AI.Anthropic"))
        .Build();

    private static readonly IObjectProvider<IType> DomainTypes =
        Types().That().ResideInNamespaceMatching("RelationshipFix\\.Domain.*").As("Domain");

    private static readonly IObjectProvider<IType> ContractTypes =
        Types().That().ResideInNamespaceMatching("RelationshipFix\\.DataContracts.*").As("DataContracts");

    private static readonly IObjectProvider<IType> EvaluationTypes =
        Types().That().ResideInNamespaceMatching("RelationshipFix\\.Evaluation.*").As("Evaluation");

    private static readonly IObjectProvider<IType> AbstractionTypes =
        Types().That().ResideInNamespaceMatching("RelationshipFix\\.AI\\.Abstractions.*").As("AI.Abstractions");

    private static readonly IObjectProvider<IType> AnthropicTypes =
        Types().That().ResideInNamespaceMatching("RelationshipFix\\.AI\\.Anthropic.*").As("AI.Anthropic");

    [Fact]
    public void Domain_does_not_depend_on_outer_layers() =>
        Types().That().Are(DomainTypes)
            .Should().NotDependOnAny(ContractTypes)
            .AndShould().NotDependOnAny(EvaluationTypes)
            .AndShould().NotDependOnAny(AbstractionTypes)
            .AndShould().NotDependOnAny(AnthropicTypes)
            .Check(Architecture);

    [Fact]
    public void DataContracts_do_not_depend_on_evaluation_or_providers() =>
        Types().That().Are(ContractTypes)
            .Should().NotDependOnAny(EvaluationTypes)
            .AndShould().NotDependOnAny(AbstractionTypes)
            .AndShould().NotDependOnAny(AnthropicTypes)
            .Check(Architecture);

    [Fact]
    public void Abstractions_do_not_depend_on_concrete_provider() =>
        Types().That().Are(AbstractionTypes)
            .Should().NotDependOnAny(AnthropicTypes)
            .Check(Architecture);

    [Fact]
    public void Evaluation_does_not_depend_on_concrete_provider() =>
        Types().That().Are(EvaluationTypes)
            .Should().NotDependOnAny(AnthropicTypes)
            .Check(Architecture);
}
