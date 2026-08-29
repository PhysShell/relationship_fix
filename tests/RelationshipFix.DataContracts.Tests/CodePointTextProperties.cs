using FsCheck;
using FsCheck.Fluent;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.DataContracts.Unicode;
using Shouldly;
using Xunit;

namespace RelationshipFix.DataContracts.Tests;

/// <summary>
/// Property-тесты контракта ADR-0002: для любого текста из «неудобных» атомов
/// (эмодзи, ZWJ-семьи, combining marks, RTL, кириллица) span, посчитанный
/// в code points, переживает сериализацию и проходит source-integrity проверку.
/// </summary>
public class CodePointTextProperties
{
    private static Gen<string> AtomGen() => Gen.Elements(
        "a", "б", "ы", "ё", "😂", "😔", "❤️",
        "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466", // ZWJ family
        "é", "ш", "ש", "س", "中", "🇰🇿",
        "!", " ", "\n", "ok", "привет", "ну ты дебил 😂❤️");

    private static Gen<(string Text, int Start, int Length)> SpanCaseGen() =>
        from parts in AtomGen().ListOf()
        let text = string.Concat(parts)
        where CodePointText.CountCodePoints(text) > 0
        let total = CodePointText.CountCodePoints(text)
        from start in Gen.Choose(0, total - 1)
        from length in Gen.Choose(1, total - start)
        select (text, start, length);

    [Fact]
    public void Span_survives_slice_serialize_deserialize_verify()
    {
        Prop.ForAll(SpanCaseGen().ToArbitrary(), testCase =>
        {
            var (text, start, length) = testCase;

            var quoted = CodePointText.SliceByCodePoints(text, start, length);
            CodePointText.CountCodePoints(quoted).ShouldBe(length);

            var dto = new EvidenceSpanDto
            {
                MessageId = "m1",
                StartCodePoint = start,
                LengthCodePoints = length,
                QuotedText = quoted,
                SourceTextSha256 = CodePointText.ComputeSha256(text),
            };

            // Через канонический JSON — координаты обязаны пережить wire без потерь.
            var roundTripped = RelationshipJson.Deserialize<EvidenceSpanDto>(RelationshipJson.Serialize(dto));
            roundTripped.ShouldBe(dto);

            var span = WireMapping.FromDto(roundTripped);
            CodePointText.TryVerifySpan(text, span, out var failure).ShouldBeTrue(failure);
        }).QuickCheckThrowOnFailure();
    }

    [Fact]
    public void Full_text_span_always_verifies()
    {
        var gen = from parts in AtomGen().ListOf()
                  let text = string.Concat(parts)
                  where CodePointText.CountCodePoints(text) > 0
                  select text;

        Prop.ForAll(gen.ToArbitrary(), text =>
        {
            var total = CodePointText.CountCodePoints(text);
            CodePointText.SliceByCodePoints(text, 0, total).ShouldBe(text);
        }).QuickCheckThrowOnFailure();
    }
}
