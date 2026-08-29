using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using NodaTime;
using NodaTime.Serialization.SystemTextJson;

namespace RelationshipFix.DataContracts;

/// <summary>
/// Единственный канонический сериализатор wire-артефактов (ADR-0002).
/// Свойства: snake_case, компактный вывод, null-поля опускаются, NodaTime — ISO-8601.
/// Экранирование (UnsafeRelaxedJsonEscaping): BMP-не-ASCII (кириллица, ❤️) пишется
/// литерально, non-BMP (😂 и прочие astral) — как \uXXXX surrogate pair. Это
/// детерминированно, валидно для любого JSON-ридера и заморожено golden fixtures;
/// канон контракта — байты, а не «красота». Ад-хок JsonSerializerOptions вне
/// этого класса запрещены архитектурным тестом.
/// </summary>
public static class RelationshipJson
{
    public static JsonSerializerOptions Options { get; } = Create();

    private static JsonSerializerOptions Create()
    {
        var options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            WriteIndented = false,
        };
        options.ConfigureForNodaTime(DateTimeZoneProviders.Tzdb);
        return options;
    }

    public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, Options);

    public static T Deserialize<T>(string json) =>
        JsonSerializer.Deserialize<T>(json, Options)
        ?? throw new InvalidOperationException($"Deserialized null for {typeof(T).Name}.");
}
