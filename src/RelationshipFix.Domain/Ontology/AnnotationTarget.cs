using System.Collections.Immutable;
using System.Security.Cryptography;
using System.Text;
using RelationshipFix.Domain.Evidence;
using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

/// <summary>
/// Ссылка на derived-единицу (turn/exchange/episode). Такие единицы — НЕ source
/// facts: их границы выводит segmentation-алгоритм, поэтому ссылка обязана нести
/// provenance: версию сегментации, состав сообщений и hash состава. Иначе смена
/// алгоритма тихо переписывает, что означал «exchange-17», а git невиновен.
/// </summary>
public sealed record DerivedUnitRef(
    DerivedUnitId UnitId,
    string SegmentationVersion,
    ImmutableArray<MessageId> MemberMessageIds,
    Sha256Hex MembersSha256)
{
    public static DerivedUnitRef Create(
        DerivedUnitId unitId,
        string segmentationVersion,
        ImmutableArray<MessageId> memberMessageIds) =>
        new(unitId, segmentationVersion, memberMessageIds, ComputeMembersSha256(memberMessageIds));

    /// <summary>
    /// Канонический hash состава: SHA-256 от UTF-8 байтов member-id, соединённых '\n',
    /// в исходном (хронологическом) порядке — состав НЕ сортируется.
    /// </summary>
    public static Sha256Hex ComputeMembersSha256(ImmutableArray<MessageId> memberMessageIds)
    {
        var canonical = string.Join("\n", memberMessageIds.Select(m => (string)m));
        return Sha256Hex.Create(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))));
    }

    public bool MembersHashIsValid() => ComputeMembersSha256(MemberMessageIds) == MembersSha256;
}

/// <summary>
/// Цель аннотации. Utterance адресуется source-фактом (MessageId); turn/exchange/
/// episode — только через provenance-aware DerivedUnitRef. Никаких «четырёх
/// nullable-id в одном объекте».
/// </summary>
[Union]
public partial record AnnotationTarget
{
    public sealed record Utterance(MessageId MessageId) : AnnotationTarget;

    public sealed record Turn(DerivedUnitRef Ref) : AnnotationTarget;

    public sealed record Exchange(DerivedUnitRef Ref) : AnnotationTarget;

    public sealed record Episode(DerivedUnitRef Ref) : AnnotationTarget;
}
