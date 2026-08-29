using Thinktecture;

namespace RelationshipFix.Domain.Evidence;

[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct MessageId
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        // Запрет control-символов держит канонизацию DerivedUnitRef ('\n'-join) однозначной.
        if (string.IsNullOrWhiteSpace(value) || value.Any(char.IsControl))
            validationError = new ValidationError("Message id must be non-empty and contain no control characters.");
    }
}

[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct DerivedUnitId
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Any(char.IsControl))
            validationError = new ValidationError("Derived unit id must be non-empty and contain no control characters.");
    }
}

[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct ParticipantId
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            validationError = new ValidationError("Participant id must be non-empty.");
    }
}

[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct AnnotatorId
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            validationError = new ValidationError("Annotator id must be non-empty.");
    }
}
