using Anthropic;
using Anthropic.Models.Messages;
using RelationshipFix.AI.Abstractions;

namespace RelationshipFix.AI.Anthropic;

/// <summary>
/// Минимальный адаптер официального Anthropic SDK. Slice его не использует
/// (там детерминированный rule-stub); адаптер существует, чтобы baseline-harness
/// имел живой provider с первого дня. Server-side refusal fallbacks сознательно
/// отложены до ADR реального LlmAnnotator.
/// </summary>
public sealed class AnthropicModelClient : IModelClient
{
    /// <summary>Дефолт по текущей политике: наиболее capable общий Opus.</summary>
    public const string DefaultModelId = "claude-opus-5";

    private readonly AnthropicClient _client;

    public AnthropicModelClient(AnthropicClient? client = null) => _client = client ?? new AnthropicClient();

    public string Provider => "anthropic";

    public ModelCapabilities Capabilities => new(SupportsNativeBatch: false, SupportsStructuredOutput: false);

    public async Task<ModelCallResult> CompleteAsync(
        ModelCallRequest request,
        CancellationToken cancellationToken = default)
    {
        // STATIC-слой (system) кэшируется; DYNAMIC (per-item) идёт в user-контент (ADR-0003 §prompt).
        var response = await _client.Messages.Create(new MessageCreateParams
        {
            Model = request.ModelId,
            MaxTokens = 16000,
            Thinking = new ThinkingConfigAdaptive(),
            System = new List<TextBlockParam>
            {
                new() { Text = request.SystemPrompt, CacheControl = new CacheControlEphemeral() },
            },
            Messages = [new() { Role = Role.User, Content = request.UserContent }],
        });

        var stopReason = response.StopReason?.ToString() ?? "unknown";
        if (stopReason.Contains("refusal", StringComparison.OrdinalIgnoreCase))
        {
            throw new ModelRefusalException(
                Provider,
                request.ModelId,
                response.StopDetails?.Category?.ToString(),
                response.StopDetails?.Explanation);
        }

        var text = string.Concat(
            response.Content.Select(b => b.Value).OfType<TextBlock>().Select(t => t.Text));

        var usage = new ModelUsage(
            response.Usage.InputTokens,
            response.Usage.OutputTokens,
            response.Usage.CacheReadInputTokens);

        return new ModelCallResult(
            text,
            stopReason,
            usage,
            Provider,
            request.ModelId,
            RawResponseJson: response.ToString() ?? "{}");
    }
}
