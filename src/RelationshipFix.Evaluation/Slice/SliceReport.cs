using System.Net;
using System.Text;
using RelationshipFix.DataContracts.Dto;

namespace RelationshipFix.Evaluation.Slice;

/// <summary>Нарочито простой отчёт: цифры контракта, без сентимент-графиков и скоров.</summary>
public static class SliceReport
{
    public static string Render(SliceMetricsDto metrics, IReadOnlyList<string> issues)
    {
        var sb = new StringBuilder();
        sb.AppendLine("<!doctype html><html><head><meta charset=\"utf-8\">");
        sb.AppendLine("<title>Relationship Microscope — slice run</title>");
        sb.AppendLine("<style>body{font-family:system-ui;margin:2rem;max-width:60rem}table{border-collapse:collapse}td,th{border:1px solid #999;padding:.3rem .6rem;text-align:left}h1{font-size:1.3rem}</style>");
        sb.AppendLine("</head><body>");
        sb.AppendLine("<h1>Slice run (rule-stub, не анализ отношений)</h1>");

        sb.AppendLine("<table><tr><th>metric</th><th>value</th></tr>");
        AppendRow(sb, "messages_total", metrics.MessagesTotal);
        AppendRow(sb, "decisions_assigned", metrics.DecisionsAssigned);
        AppendRow(sb, "decisions_none_observed", metrics.DecisionsNoneObserved);
        AppendRow(sb, "decisions_abstained", metrics.DecisionsAbstained);
        AppendRow(sb, "spans_checked", metrics.SpansChecked);
        AppendRow(sb, "spans_valid", metrics.SpansValid);
        AppendRow(sb, "validation_issues", metrics.AnnotationValidationIssues);
        sb.AppendLine("</table>");

        sb.AppendLine("<h2>Labels</h2><table><tr><th>label</th><th>count</th></tr>");
        foreach (var (label, count) in metrics.LabelCounts)
            AppendRow(sb, label, count);
        sb.AppendLine("</table>");

        if (metrics.AbstentionReasons.Count > 0)
        {
            sb.AppendLine("<h2>Abstentions</h2><table><tr><th>reason</th><th>count</th></tr>");
            foreach (var (reason, count) in metrics.AbstentionReasons)
                AppendRow(sb, reason, count);
            sb.AppendLine("</table>");
        }

        if (issues.Count > 0)
        {
            sb.AppendLine("<h2>Validation issues</h2><ul>");
            foreach (var issue in issues)
                sb.AppendLine($"<li>{WebUtility.HtmlEncode(issue)}</li>");
            sb.AppendLine("</ul>");
        }

        sb.AppendLine("</body></html>");
        return sb.ToString();
    }

    private static void AppendRow(StringBuilder sb, string name, int value) =>
        sb.AppendLine($"<tr><td>{WebUtility.HtmlEncode(name)}</td><td>{value}</td></tr>");
}
