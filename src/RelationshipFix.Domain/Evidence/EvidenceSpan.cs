namespace RelationshipFix.Domain.Evidence;

/// <summary>
/// Указатель на фрагмент исходного сообщения. Несёт избыточность намеренно:
/// QuotedText и SourceTextSha256 позволяют source-integrity проверке поймать
/// и смещение offsets, и подмену исходного текста (evaluation contract §2.4).
/// Offsets вычисляются по исходной строке ДО какой-либо нормализации.
/// </summary>
public sealed record EvidenceSpan(
    MessageId MessageId,
    CodePointOffset StartCodePoint,
    CodePointLength LengthCodePoints,
    string QuotedText,
    Sha256Hex SourceTextSha256);
