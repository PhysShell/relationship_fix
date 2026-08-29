using RelationshipFix.Domain.Ontology;

namespace RelationshipFix.Evaluation.Ontology;

/// <summary>
/// Онтология — machine-readable constraint, не только документация.
/// Валидатор ловит структурные проблемы до того, как они превратятся
/// в несравнимые разметки.
/// </summary>
public static class OntologyValidator
{
    public static IReadOnlyList<string> Validate(BehaviorOntology ontology)
    {
        var issues = new List<string>();
        var ids = new HashSet<BehaviorLabelId>();

        foreach (var label in ontology.Labels)
        {
            if (!ids.Add(label.Id))
                issues.Add($"{label.Id}: duplicate label id.");

            if (label.AllowedUnits.IsDefaultOrEmpty)
                issues.Add($"{label.Id}: allowed_units must be non-empty.");

            if (string.IsNullOrWhiteSpace(label.OperationalDefinition))
                issues.Add($"{label.Id}: operational_definition is required.");

            foreach (var example in label.Examples)
            {
                if (!label.AllowsUnit(example.Unit))
                    issues.Add($"{label.Id}: example uses unit '{example.Unit}' not in allowed_units.");
                if (example.Language is not ("ru" or "en"))
                    issues.Add($"{label.Id}: example language '{example.Language}' is not a working language (ru/en).");
            }

            // Протокол v0: у каждого label должны быть примеры на обоих рабочих языках.
            foreach (var lang in (string[])["ru", "en"])
            {
                if (!label.Examples.Any(e => e.Language == lang))
                    issues.Add($"{label.Id}: missing examples for language '{lang}'.");
            }

            if (!label.Examples.Any(e => e.Verdict == ExampleVerdict.Positive) ||
                !label.Examples.Any(e => e.Verdict == ExampleVerdict.Negative))
            {
                issues.Add($"{label.Id}: needs at least one positive and one negative example.");
            }
        }

        // Ссылочная целостность confusable_with — после сбора всех id.
        foreach (var label in ontology.Labels)
        {
            foreach (var reference in label.ConfusableWith)
            {
                if (!ids.Contains(reference))
                    issues.Add($"{label.Id}: confusable_with references unknown label '{reference}'.");
            }
        }

        return issues;
    }

    /// <summary>Проверка аннотации против онтологии (labels существуют, единица допустима, evidence на месте).</summary>
    public static IReadOnlyList<string> ValidateAnnotation(BehaviorOntology ontology, UnitAnnotation annotation)
    {
        var issues = new List<string>();

        annotation.Decision.Switch(
            assigned: a =>
            {
                if (a.Labels.IsDefaultOrEmpty)
                    issues.Add("assigned decision must carry at least one label.");

                foreach (var labelId in a.Labels)
                {
                    var label = ontology.Find(labelId);
                    if (label is null)
                    {
                        issues.Add($"unknown label '{labelId}'.");
                        continue;
                    }

                    if (!label.AllowsUnit(annotation.Unit))
                        issues.Add($"label '{labelId}' is not allowed on unit '{annotation.Unit}'.");

                    if (label.EvidenceRequired && a.Evidence.IsDefaultOrEmpty)
                        issues.Add($"label '{labelId}' requires evidence spans.");
                }
            },
            noneObserved: _ => { },
            abstained: _ => { });

        return issues;
    }
}
