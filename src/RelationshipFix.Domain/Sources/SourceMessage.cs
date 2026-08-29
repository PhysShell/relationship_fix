using RelationshipFix.Domain.Evidence;

namespace RelationshipFix.Domain.Sources;

/// <summary>
/// Immutable исходное сообщение. Text хранится как есть — без нормализации,
/// без trim: любые производные представления считаются derived, не source.
/// </summary>
public sealed record SourceMessage(
    MessageId Id,
    ParticipantId Author,
    SourceTimestamp Timestamp,
    string Text);
