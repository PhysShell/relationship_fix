using System.Text.RegularExpressions;
using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Идентификатор behavior label (namespace B.*). Transition labels (T.*) — отдельный
/// тип, появится когда начнём выводить переходы; их нельзя смешивать с B.*.
/// </summary>
[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct BehaviorLabelId
{
    private static readonly Regex Pattern = new("^B\\.[A-Z][A-Z0-9_]*$", RegexOptions.Compiled);

    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        if (string.IsNullOrWhiteSpace(value) || !Pattern.IsMatch(value))
        {
            validationError = new ValidationError(
                $"Behavior label id must match ^B.[A-Z][A-Z0-9_]*$, got '{value}'.");
        }
    }
}
