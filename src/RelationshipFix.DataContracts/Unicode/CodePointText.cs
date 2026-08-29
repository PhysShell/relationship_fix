using System.Security.Cryptography;
using System.Text;
using RelationshipFix.Domain.Evidence;

namespace RelationshipFix.DataContracts.Unicode;

/// <summary>
/// ADR-0002: все span-операции идут через Unicode code points (Rune),
/// никогда через индексацию string[i] (UTF-16 code units). Никакой нормализации
/// исходного текста перед вычислением offsets.
/// </summary>
public static class CodePointText
{
    public static int CountCodePoints(string text)
    {
        var count = 0;
        foreach (var _ in text.EnumerateRunes())
            count++;
        return count;
    }

    /// <summary>Срез по code-point координатам. Бросает ArgumentOutOfRangeException на невалидном диапазоне.</summary>
    public static string SliceByCodePoints(string text, int startCodePoint, int lengthCodePoints)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(startCodePoint);
        ArgumentOutOfRangeException.ThrowIfNegative(lengthCodePoints);

        var utf16Start = -1;
        var utf16End = -1;
        var cpIndex = 0;
        var utf16Index = 0;

        foreach (var rune in text.EnumerateRunes())
        {
            if (cpIndex == startCodePoint)
                utf16Start = utf16Index;
            if (cpIndex == startCodePoint + lengthCodePoints)
            {
                utf16End = utf16Index;
                break;
            }

            utf16Index += rune.Utf16SequenceLength;
            cpIndex++;
        }

        // Диапазон может заканчиваться ровно на конце строки.
        if (utf16Start < 0 && cpIndex == startCodePoint)
            utf16Start = utf16Index;
        if (utf16End < 0 && cpIndex == startCodePoint + lengthCodePoints)
            utf16End = utf16Index;

        if (utf16Start < 0 || utf16End < 0)
            throw new ArgumentOutOfRangeException(
                nameof(startCodePoint),
                $"Range [{startCodePoint}, +{lengthCodePoints}) is outside of a {cpIndex}-code-point string.");

        return text[utf16Start..utf16End];
    }

    /// <summary>Перевод UTF-16 индекса (например, из string.IndexOf) в code-point индекс.</summary>
    public static int Utf16IndexToCodePointIndex(string text, int utf16Index)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(utf16Index);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(utf16Index, text.Length);

        var cpIndex = 0;
        var pos = 0;
        foreach (var rune in text.EnumerateRunes())
        {
            if (pos >= utf16Index)
                break;
            pos += rune.Utf16SequenceLength;
            cpIndex++;
        }

        if (pos != utf16Index)
            throw new ArgumentException(
                $"UTF-16 index {utf16Index} splits a surrogate pair.", nameof(utf16Index));

        return cpIndex;
    }

    public static Sha256Hex ComputeSha256(string text)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(text));
        return Sha256Hex.Create(Convert.ToHexStringLower(hash));
    }

    /// <summary>
    /// Source-integrity проверка (evaluation contract §2.4): hash исходного текста,
    /// срез по code points и точное сравнение с QuotedText.
    /// </summary>
    public static bool TryVerifySpan(string sourceText, EvidenceSpan span, out string? failure)
    {
        if (ComputeSha256(sourceText) != span.SourceTextSha256)
        {
            failure = "source text hash mismatch";
            return false;
        }

        string sliced;
        try
        {
            sliced = SliceByCodePoints(sourceText, span.StartCodePoint, span.LengthCodePoints);
        }
        catch (ArgumentOutOfRangeException)
        {
            failure = "span range outside of source text";
            return false;
        }

        if (!string.Equals(sliced, span.QuotedText, StringComparison.Ordinal))
        {
            failure = $"quoted text mismatch: expected '{span.QuotedText}', sliced '{sliced}'";
            return false;
        }

        failure = null;
        return true;
    }
}
