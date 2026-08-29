namespace RelationshipFix.AI.Abstractions;

/// <summary>
/// Параметры инференса — provider-specific bag (ADR-0003): у разных провайдеров
/// разные ручки (thinking/effort/…), и manifest фиксирует их как есть,
/// не притворяясь, что «temperature» универсальна.
/// </summary>
public sealed record ModelCallRequest(
    string ModelId,
    string SystemPrompt,
    string UserContent,
    IReadOnlyDictionary<string, string> InferenceParams);

public sealed record ModelUsage(long InputTokens, long OutputTokens, long? CachedInputTokens);

public sealed record ModelCallResult(
    string Text,
    string StopReason,
    ModelUsage Usage,
    string Provider,
    string ModelId,
    string RawResponseJson);

public sealed record ModelCapabilities(bool SupportsNativeBatch, bool SupportsStructuredOutput);

/// <summary>Провайдеро-независимый клиент. Baseline A/B/C гоняется через этот интерфейс.</summary>
public interface IModelClient
{
    string Provider { get; }

    ModelCapabilities Capabilities { get; }

    Task<ModelCallResult> CompleteAsync(ModelCallRequest request, CancellationToken cancellationToken = default);
}

/// <summary>
/// Batch — capability-интерфейс, а не обязательный метод: адаптер без нативного
/// batch не обязан его эмулировать; harness сам решает
/// (native batch | bounded parallel individual calls).
/// </summary>
public interface IBatchModelClient : IModelClient
{
    Task<IReadOnlyList<ModelCallResult>> CompleteBatchAsync(
        IReadOnlyList<ModelCallRequest> requests,
        CancellationToken cancellationToken = default);
}

/// <summary>Модель отказалась отвечать (stop_reason=refusal и аналоги) — это не транспортная ошибка.</summary>
public sealed class ModelRefusalException(string provider, string modelId, string? category, string? explanation)
    : Exception($"Model {provider}/{modelId} refused: {category ?? "unknown"} — {explanation ?? "no explanation"}")
{
    public string Provider { get; } = provider;
    public string ModelId { get; } = modelId;
    public string? Category { get; } = category;
    public string? Explanation { get; } = explanation;
}
