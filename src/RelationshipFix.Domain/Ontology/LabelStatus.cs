using Thinktecture;

namespace RelationshipFix.Domain.Ontology;

[SmartEnum<string>]
public partial class LabelStatus
{
    public static readonly LabelStatus Draft = new("draft");
    public static readonly LabelStatus Active = new("active");
    public static readonly LabelStatus Retired = new("retired");
}
