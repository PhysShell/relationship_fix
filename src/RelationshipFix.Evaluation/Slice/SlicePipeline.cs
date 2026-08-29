using NodaTime;
using RelationshipFix.DataContracts;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.DataContracts.Jsonl;
using RelationshipFix.DataContracts.Unicode;
using RelationshipFix.Domain.Ontology;
using RelationshipFix.Domain.Sources;
using RelationshipFix.Evaluation.Ontology;
using RelationshipFix.Evaluation.Provenance;

namespace RelationshipFix.Evaluation.Slice;

public sealed record SliceResult(
    string RunDirectory,
    SliceMetricsDto Metrics,
    IReadOnlyList<string> ValidationIssues);

/// <summary>
/// Уродливый vertical slice (roadmap, этап 2-минус): fixture → stub annotation →
/// validation → JSONL → metrics → report + manifest. Ценность — в прогоне всего
/// контракта данных, не в качестве анализа.
/// </summary>
public static class SlicePipeline
{
    public static SliceResult Run(
        string fixtureMessagesPath,
        string ontologyPath,
        string outDirectory,
        ISliceAnnotator annotator,
        string? workingDirectoryForGit = null)
    {
        Directory.CreateDirectory(outDirectory);

        var ontology = OntologyLoader.Load(ontologyPath);
        var messages = Jsonl.ReadAllLines<SourceMessageDto>(fixtureMessagesPath)
            .Select(WireMapping.FromDto)
            .ToList();

        // 1. Annotate.
        var annotations = messages.Select(annotator.Annotate).ToList();

        // 2. Validate против онтологии + source-integrity spans.
        var issues = new List<string>();
        var spansChecked = 0;
        var spansValid = 0;
        var messageById = messages.ToDictionary(m => m.Id);

        foreach (var annotation in annotations)
        {
            foreach (var issue in OntologyValidator.ValidateAnnotation(ontology, annotation))
                issues.Add($"{annotation.MessageId}: {issue}");

            annotation.Decision.Switch(
                assigned: a =>
                {
                    foreach (var span in a.Evidence)
                    {
                        spansChecked++;
                        var source = messageById[span.MessageId];
                        if (CodePointText.TryVerifySpan(source.Text, span, out var failure))
                            spansValid++;
                        else
                            issues.Add($"{annotation.MessageId}: span integrity failed — {failure}");
                    }
                },
                noneObserved: _ => { },
                abstained: _ => { });
        }

        // 3. Персистим артефакты (только через canonical writer).
        var annotationDtos = annotations.Select(WireMapping.ToDto).ToList();
        Jsonl.WriteAllLines(Path.Combine(outDirectory, "annotations.jsonl"), annotationDtos);

        var metrics = BuildMetrics(annotations, annotationDtos, spansChecked, spansValid, issues.Count);
        File.WriteAllText(
            Path.Combine(outDirectory, "metrics.json"),
            RelationshipJson.Serialize(metrics));

        var manifest = RunProvenance.BuildManifest(
            runId: Path.GetFileName(outDirectory.TrimEnd(Path.DirectorySeparatorChar)),
            startedAt: SystemClock.Instance.GetCurrentInstant(),
            workingDirectory: workingDirectoryForGit ?? Directory.GetCurrentDirectory(),
            ontologyVersion: ontology.Version,
            ontologyPath: ontologyPath,
            datasetId: Path.GetFileName(fixtureMessagesPath),
            datasetPath: fixtureMessagesPath,
            annotatorId: annotator.Id);
        File.WriteAllText(
            Path.Combine(outDirectory, "manifest.json"),
            RelationshipJson.Serialize(manifest));

        File.WriteAllText(
            Path.Combine(outDirectory, "report.html"),
            SliceReport.Render(metrics, issues));

        return new SliceResult(outDirectory, metrics, issues);
    }

    private static SliceMetricsDto BuildMetrics(
        IReadOnlyList<UnitAnnotation> annotations,
        IReadOnlyList<AnnotationDto> dtos,
        int spansChecked,
        int spansValid,
        int issueCount)
    {
        var labelCounts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        var abstentionReasons = new SortedDictionary<string, int>(StringComparer.Ordinal);
        int assigned = 0, none = 0, abstainedCount = 0;

        foreach (var annotation in annotations)
        {
            annotation.Decision.Switch(
                assigned: a =>
                {
                    assigned++;
                    foreach (var label in a.Labels)
                    {
                        var key = (string)label;
                        labelCounts[key] = labelCounts.GetValueOrDefault(key) + 1;
                    }
                },
                noneObserved: _ => none++,
                abstained: a =>
                {
                    abstainedCount++;
                    var key = a.Reason.Key;
                    abstentionReasons[key] = abstentionReasons.GetValueOrDefault(key) + 1;
                });
        }

        return new SliceMetricsDto
        {
            SchemaVersion = WireSchema.SliceMetricsV1,
            MessagesTotal = dtos.Count,
            DecisionsAssigned = assigned,
            DecisionsNoneObserved = none,
            DecisionsAbstained = abstainedCount,
            LabelCounts = labelCounts,
            AbstentionReasons = abstentionReasons,
            SpansChecked = spansChecked,
            SpansValid = spansValid,
            AnnotationValidationIssues = issueCount,
        };
    }
}
