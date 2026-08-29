using System.Diagnostics;
using System.Security.Cryptography;
using NodaTime;
using RelationshipFix.DataContracts.Dto;

namespace RelationshipFix.Evaluation.Provenance;

/// <summary>
/// ADR-0003: manifest фиксирует provenance/конфигурацию запуска. Он гарантирует
/// воспроизводимость происхождения (что именно было отправлено/посчитано),
/// а не побитовое воспроизведение LLM-вывода.
/// </summary>
public static class RunProvenance
{
    public static string Sha256OfFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    public static GitInfoDto ReadGitInfo(string workingDirectory)
    {
        var commit = TryRunGit(workingDirectory, "rev-parse HEAD") ?? "unknown";
        var status = TryRunGit(workingDirectory, "status --porcelain");
        return new GitInfoDto
        {
            Commit = commit,
            Dirty = !string.IsNullOrWhiteSpace(status),
        };
    }

    public static RunManifestDto BuildManifest(
        string runId,
        Instant startedAt,
        string workingDirectory,
        string ontologyVersion,
        string ontologyPath,
        string datasetId,
        string datasetPath,
        string annotatorId) => new()
    {
        SchemaVersion = RelationshipFix.DataContracts.WireSchema.RunManifestV1,
        RunId = runId,
        StartedAt = startedAt,
        Git = ReadGitInfo(workingDirectory),
        Ontology = new ArtifactRefDto { Id = ontologyVersion, Sha256 = Sha256OfFile(ontologyPath) },
        Dataset = new ArtifactRefDto { Id = datasetId, Sha256 = Sha256OfFile(datasetPath) },
        AnnotatorId = annotatorId,
    };

    private static string? TryRunGit(string workingDirectory, string arguments)
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = "git",
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            });
            if (process is null)
                return null;

            var output = process.StandardOutput.ReadToEnd().Trim();
            process.WaitForExit(5000);
            return process.ExitCode == 0 ? output : null;
        }
        catch (Exception)
        {
            return null;
        }
    }
}
