using NodaTime;
using Thinktecture;

namespace RelationshipFix.Domain.Sources;

/// <summary>
/// Temporal provenance хранится так же строго, как text provenance (ADR-0002):
/// если экспорт не содержит надёжной timezone-информации, мы не превращаем
/// «14:32» в притворно точный Instant.
/// </summary>
[Union]
public partial record SourceTimestamp
{
    public sealed record ExactInstant(Instant Value) : SourceTimestamp;

    public sealed record LocalWithAssumedZone(LocalDateTime Value, string ZoneId) : SourceTimestamp;

    public sealed record LocalUnknownZone(LocalDateTime Value) : SourceTimestamp;
}
