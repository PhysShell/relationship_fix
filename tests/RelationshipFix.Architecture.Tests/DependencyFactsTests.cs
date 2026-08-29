using System.Reflection;
using Shouldly;
using Xunit;

namespace RelationshipFix.Architecture.Tests;

/// <summary>
/// ADR-0001: границы зависимостей — не договорённость, а падающий тест.
/// GetReferencedAssemblies показывает только реально используемые ссылки,
/// поэтому проверка точна и для «не установленных» запретов (LanguageExt).
/// </summary>
public class DependencyFactsTests
{
    private static AssemblyName[] Refs(string assemblyName) =>
        Assembly.Load(assemblyName).GetReferencedAssemblies();

    private static void ShouldNotReference(string assembly, params string[] forbiddenPrefixes)
    {
        var offending = Refs(assembly)
            .Where(r => forbiddenPrefixes.Any(p =>
                r.Name!.StartsWith(p, StringComparison.OrdinalIgnoreCase)))
            .Select(r => r.Name)
            .ToArray();

        offending.ShouldBeEmpty(
            $"{assembly} must not reference [{string.Join(", ", forbiddenPrefixes)}], found: {string.Join(", ", offending)}");
    }

    [Fact]
    public void Domain_references_only_Thinktecture_NodaTime_and_BCL()
    {
        ShouldNotReference("RelationshipFix.Domain",
            "RelationshipFix.DataContracts",
            "RelationshipFix.Evaluation",
            "RelationshipFix.AI",
            "RelationshipFix.Cli",
            "LanguageExt",
            "Spectre",
            "Anthropic",
            "System.Text.Json");
    }

    [Fact]
    public void DataContracts_is_the_only_project_referencing_SystemTextJson()
    {
        foreach (var assembly in (string[])
                 [
                     "RelationshipFix.Domain",
                     "RelationshipFix.Evaluation",
                     "RelationshipFix.AI.Abstractions",
                 ])
        {
            ShouldNotReference(assembly, "System.Text.Json");
        }

        Refs("RelationshipFix.DataContracts")
            .ShouldContain(r => r.Name == "System.Text.Json");
    }

    [Fact]
    public void AiAbstractions_are_provider_free()
    {
        ShouldNotReference("RelationshipFix.AI.Abstractions",
            "Anthropic", "RelationshipFix.AI.Anthropic", "RelationshipFix.DataContracts", "RelationshipFix.Domain");
    }

    [Fact]
    public void Only_Cli_may_reference_Spectre()
    {
        foreach (var assembly in (string[])
                 [
                     "RelationshipFix.Domain",
                     "RelationshipFix.DataContracts",
                     "RelationshipFix.Evaluation",
                     "RelationshipFix.AI.Abstractions",
                     "RelationshipFix.AI.Anthropic",
                 ])
        {
            ShouldNotReference(assembly, "Spectre");
        }
    }

    [Fact]
    public void Evaluation_does_not_reference_providers()
    {
        ShouldNotReference("RelationshipFix.Evaluation", "Anthropic", "RelationshipFix.AI.Anthropic");
    }

    [Fact]
    public void No_project_references_extra_result_frameworks()
    {
        foreach (var assembly in (string[])
                 [
                     "RelationshipFix.Domain",
                     "RelationshipFix.DataContracts",
                     "RelationshipFix.Evaluation",
                     "RelationshipFix.AI.Abstractions",
                     "RelationshipFix.AI.Anthropic",
                 ])
        {
            ShouldNotReference(assembly,
                "LanguageExt", "ErrorOr", "FluentResults", "OneOf", "CSharpFunctionalExtensions", "Vogen");
        }
    }
}
