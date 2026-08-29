using RelationshipFix.DataContracts;
using RelationshipFix.DataContracts.Dto;
using RelationshipFix.DataContracts.Jsonl;
using RelationshipFix.Evaluation.Slice;
using Shouldly;
using Xunit;

namespace RelationshipFix.E2E.Tests;

/// <summary>
/// Уродливый vertical slice целиком: fixture → stub annotation → validation →
/// JSONL → metrics → manifest → report. Пока этот тест зелёный, контракт данных
/// исполняется сквозняком, а не по кусочкам.
/// </summary>
public class SliceEndToEndTests
{
    [Fact]
    public void Slice_runs_on_repo_fixture_and_produces_valid_artifacts()
    {
        var root = FindRepoRoot();
        var outDir = Path.Combine(Path.GetTempPath(), $"rf-e2e-{Guid.NewGuid():N}");

        try
        {
            var result = SlicePipeline.Run(
                Path.Combine(root, "data", "fixtures", "slice-001", "messages.jsonl"),
                Path.Combine(root, "data", "ontology", "behavior-v0.1.json"),
                outDir,
                new RuleStubAnnotator(),
                workingDirectoryForGit: root);

            result.ValidationIssues.ShouldBeEmpty();

            var metrics = result.Metrics;
            metrics.MessagesTotal.ShouldBe(10);
            metrics.DecisionsAssigned.ShouldBe(6);
            metrics.DecisionsNoneObserved.ShouldBe(3);
            metrics.DecisionsAbstained.ShouldBe(1);
            metrics.SpansChecked.ShouldBeGreaterThan(0);
            metrics.SpansValid.ShouldBe(metrics.SpansChecked);

            // Playful insult «ну ты дебил 😂❤️» (m005) не должен получить blame:
            var annotations = Jsonl.ReadAllLines<AnnotationV2Dto>(Path.Combine(outDir, "annotations.jsonl"));
            var m005 = annotations.Single(a => a.Target.MessageId == "m005");
            m005.SchemaVersion.ShouldBe(WireSchema.AnnotationV2);
            m005.Target.Kind.ShouldBe("utterance");
            m005.Decision.ShouldBe("none_observed");

            // Артефакты запуска (ADR-0003) на месте и парсятся канонически.
            var manifest = RelationshipJson.Deserialize<RunManifestDto>(
                File.ReadAllText(Path.Combine(outDir, "manifest.json")));
            manifest.SchemaVersion.ShouldBe(WireSchema.RunManifestV1);
            manifest.Git.Commit.ShouldNotBeNullOrWhiteSpace();
            manifest.Ontology.Sha256.Length.ShouldBe(64);
            manifest.Dataset.Sha256.Length.ShouldBe(64);
            manifest.AnnotatorId.ShouldBe(RuleStubAnnotator.AnnotatorIdValue);

            File.Exists(Path.Combine(outDir, "report.html")).ShouldBeTrue();
        }
        finally
        {
            if (Directory.Exists(outDir))
                Directory.Delete(outDir, recursive: true);
        }
    }

    private static string FindRepoRoot()
    {
        var dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "RelationshipFix.slnx")))
            dir = Path.GetDirectoryName(dir);
        return dir ?? throw new InvalidOperationException("RelationshipFix.slnx not found above test directory.");
    }
}
