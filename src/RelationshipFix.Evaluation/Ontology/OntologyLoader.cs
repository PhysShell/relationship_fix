using RelationshipFix.DataContracts;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.Domain.Ontology;

namespace RelationshipFix.Evaluation.Ontology;

public static class OntologyLoader
{
    public static BehaviorOntology Load(string path)
    {
        var dto = RelationshipJson.Deserialize<OntologyFileDto>(File.ReadAllText(path));
        var ontology = WireMapping.OntologyFromDto(dto);
        var issues = OntologyValidator.Validate(ontology);
        if (issues.Count > 0)
        {
            throw new InvalidOperationException(
                "Ontology validation failed:\n" + string.Join("\n", issues.Select(i => $"- {i}")));
        }

        return ontology;
    }
}
