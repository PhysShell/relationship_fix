using RelationshipFix.DataContracts.Unicode;
using RelationshipFix.Domain.Evidence;
using Shouldly;
using Xunit;

namespace RelationshipFix.DataContracts.Tests;

public class CodePointTextTests
{
    [Fact]
    public void Emoji_counts_as_one_code_point()
    {
        // "a😂b": 3 code points, но 4 UTF-16 units — канонический минимальный контрпример.
        CodePointText.CountCodePoints("a😂b").ShouldBe(3);
        CodePointText.SliceByCodePoints("a😂b", 1, 1).ShouldBe("😂");
        CodePointText.SliceByCodePoints("a😂b", 2, 1).ShouldBe("b");
    }

    [Fact]
    public void Zwj_family_is_multiple_code_points_and_slices_exactly()
    {
        // 👨‍👩‍👧‍👦 = 7 code points (4 emoji + 3 ZWJ). Мы считаем code points, не графемы — намеренно.
        const string family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466";
        CodePointText.CountCodePoints(family).ShouldBe(7);
        CodePointText.SliceByCodePoints(family, 0, 7).ShouldBe(family);
    }

    [Fact]
    public void Combining_mark_is_separate_code_point()
    {
        const string text = "éx"; // e + combining acute + x
        CodePointText.CountCodePoints(text).ShouldBe(3);
        CodePointText.SliceByCodePoints(text, 0, 2).ShouldBe("é");
    }

    [Fact]
    public void Rtl_text_slices_by_logical_order()
    {
        const string text = "שלום עולם";
        CodePointText.SliceByCodePoints(text, 0, 4).ShouldBe("שלום");
    }

    [Fact]
    public void Verify_fails_on_tampered_hash()
    {
        const string source = "Ты всегда 😂";
        var span = new EvidenceSpan(
            MessageId.Create("m1"),
            CodePointOffset.Create(3),
            CodePointLength.Create(6),
            "всегда",
            Sha256Hex.Create(new string('0', 64)));

        CodePointText.TryVerifySpan(source, span, out var failure).ShouldBeFalse();
        failure.ShouldNotBeNull();
        failure.ShouldContain("hash");
    }

    [Fact]
    public void Verify_fails_on_out_of_range_span()
    {
        const string source = "ok";
        var span = new EvidenceSpan(
            MessageId.Create("m1"),
            CodePointOffset.Create(1),
            CodePointLength.Create(5),
            "k",
            CodePointText.ComputeSha256(source));

        CodePointText.TryVerifySpan(source, span, out var failure).ShouldBeFalse();
        failure.ShouldNotBeNull();
        failure.ShouldContain("range");
    }

    [Fact]
    public void Utf16_index_inside_surrogate_pair_throws()
    {
        Should.Throw<ArgumentException>(() => CodePointText.Utf16IndexToCodePointIndex("😂", 1));
    }
}
