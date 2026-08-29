using Thinktecture;

namespace RelationshipFix.Domain.Evidence;

// ADR-0002: канонические offsets считаются в Unicode code points (scalar values),
// НЕ в UTF-16 code units и не в байтах. C#-строка индексируется UTF-16 units,
// поэтому любое преобразование делается через System.Text.Rune, не string[i].

[ValueObject<int>]
public readonly partial struct CodePointOffset
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref int value)
    {
        if (value < 0)
            validationError = new ValidationError("Code point offset must be >= 0.");
    }
}

[ValueObject<int>]
public readonly partial struct CodePointLength
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref int value)
    {
        if (value < 1)
            validationError = new ValidationError("Evidence span must cover at least one code point.");
    }
}

[ValueObject<string>]
[KeyMemberEqualityComparer<ComparerAccessors.StringOrdinal, string>]
[KeyMemberComparer<ComparerAccessors.StringOrdinal, string>]
public readonly partial struct Sha256Hex
{
    static partial void ValidateFactoryArguments(ref ValidationError? validationError, ref string value)
    {
        if (value.Length != 64 || !value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'))
            validationError = new ValidationError("SHA-256 must be 64 lowercase hex chars.");
    }
}
