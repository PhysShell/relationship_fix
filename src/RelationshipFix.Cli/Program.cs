using System.CommandLine;
using RelationshipFix.Evaluation.Ontology;
using RelationshipFix.Evaluation.Slice;
using Spectre.Console;

var ontologyOption = new Option<FileInfo>("--ontology")
{
    Description = "Путь к файлу онтологии (rf.ontology.v1 JSON).",
    Required = true,
};

var fixtureOption = new Option<FileInfo>("--messages")
{
    Description = "Путь к messages.jsonl (rf.source-message.v1).",
    Required = true,
};

var outOption = new Option<DirectoryInfo>("--out")
{
    Description = "Каталог run-артефактов (annotations/metrics/manifest/report).",
    Required = true,
};

var sliceCommand = new Command("slice", "Прогнать уродливый vertical slice на fixture (rule-stub, без LLM).");
sliceCommand.Options.Add(fixtureOption);
sliceCommand.Options.Add(ontologyOption);
sliceCommand.Options.Add(outOption);
sliceCommand.SetAction(parseResult =>
{
    var messages = parseResult.GetRequiredValue(fixtureOption);
    var ontology = parseResult.GetRequiredValue(ontologyOption);
    var outDir = parseResult.GetRequiredValue(outOption);

    var result = SlicePipeline.Run(
        messages.FullName,
        ontology.FullName,
        outDir.FullName,
        new RuleStubAnnotator());

    var table = new Table().AddColumns("metric", "value");
    table.AddRow("messages_total", result.Metrics.MessagesTotal.ToString());
    table.AddRow("assigned", result.Metrics.DecisionsAssigned.ToString());
    table.AddRow("none_observed", result.Metrics.DecisionsNoneObserved.ToString());
    table.AddRow("abstained", result.Metrics.DecisionsAbstained.ToString());
    table.AddRow("spans_valid / checked", $"{result.Metrics.SpansValid} / {result.Metrics.SpansChecked}");
    table.AddRow("validation_issues", result.Metrics.AnnotationValidationIssues.ToString());
    AnsiConsole.Write(table);
    AnsiConsole.MarkupLine($"[green]Artifacts:[/] {result.RunDirectory}");

    return result.ValidationIssues.Count == 0 ? 0 : 1;
});

var ontologyArgument = new Argument<FileInfo>("path")
{
    Description = "Путь к файлу онтологии.",
};

var validateCommand = new Command("validate-ontology", "Проверить файл онтологии (структура, единицы, двуязычные примеры).");
validateCommand.Arguments.Add(ontologyArgument);
validateCommand.SetAction(parseResult =>
{
    var path = parseResult.GetRequiredValue(ontologyArgument);
    try
    {
        var ontology = OntologyLoader.Load(path.FullName);
        AnsiConsole.MarkupLine(
            $"[green]OK[/]: ontology '{ontology.Version}', labels: {ontology.Labels.Length}");
        return 0;
    }
    catch (Exception ex)
    {
        AnsiConsole.MarkupLine($"[red]INVALID[/]: {ex.Message.EscapeMarkup()}");
        return 1;
    }
});

var root = new RootCommand("relationship-fix — research CLI (Relationship Microscope, этапы 0–2).");
root.Subcommands.Add(sliceCommand);
root.Subcommands.Add(validateCommand);

return root.Parse(args).Invoke();
