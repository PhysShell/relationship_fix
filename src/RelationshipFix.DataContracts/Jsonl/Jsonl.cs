namespace RelationshipFix.DataContracts.Jsonl;

/// <summary>JSONL: одна каноническая JSON-запись на строку, UTF-8 без BOM, LF.</summary>
public static class Jsonl
{
    public static void WriteAllLines<T>(string path, IEnumerable<T> records)
    {
        using var writer = new StreamWriter(path, append: false, new System.Text.UTF8Encoding(false));
        writer.NewLine = "\n";
        foreach (var record in records)
            writer.WriteLine(RelationshipJson.Serialize(record));
    }

    public static IReadOnlyList<T> ReadAllLines<T>(string path) =>
        File.ReadLines(path)
            .Where(line => !string.IsNullOrWhiteSpace(line))
            .Select(RelationshipJson.Deserialize<T>)
            .ToList();
}
