using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class KFPSLiverySudio
{
    private const string ReportFormat = "kfps-studio-launch-check-v1";
    private const int CheckTimeoutMs = 30000;

    private sealed class Options
    {
        internal bool Check;
        internal string Report;
        internal string Workspace = null;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Options options = new Options();
        try
        {
            Parse(args, options);
            if (options.Check) ValidateReport(options.Report);
            string root = ResolveRoot(AppDomain.CurrentDomain.BaseDirectory, options.Workspace);
            string studio = options.Workspace == null
                ? Path.Combine(root, "tools", "livery-studio")
                : Path.Combine(Path.GetDirectoryName(root), "livery");
            string entry = Path.Combine(studio, "src", "launch_studio.py");
            string python = Path.Combine(root, "python", "python.exe");
            if (!File.Exists(entry))
                throw new InvalidOperationException("Livery Studio is missing. Keep this launcher beside the complete KFPS installation, including tools/livery-studio.");
            if (!File.Exists(python))
                throw new InvalidOperationException("The KFPS bundled Python runtime is missing. Repair this installation; a system Python will not be used.");

            List<string> arguments = new List<string> { "-I", "-B", entry, "--kfps-root", root };
            if (options.Workspace != null) arguments.Add("--workspace-layout");
            if (options.Check) arguments.AddRange(new[] { "--check", "--report", options.Report });
            ProcessStartInfo info = new ProcessStartInfo {
                FileName = python, Arguments = string.Join(" ", arguments.Select(Quote)),
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true
            };
            foreach (string key in info.EnvironmentVariables.Keys.Cast<string>().ToArray())
            {
                string upper = key.ToUpperInvariant();
                if (upper.StartsWith("PYTHON") || upper.StartsWith("QT_") || upper.StartsWith("QTWEBENGINE")
                    || upper.StartsWith("QML") || upper.StartsWith("PYSIDE") || upper.StartsWith("SHIBOKEN")
                    || upper.StartsWith("QSG_") || upper == "KFPS_PYTHON")
                    info.EnvironmentVariables.Remove(key);
            }
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            StringBuilder output = new StringBuilder(), error = new StringBuilder();
            using (Process process = new Process())
            {
                process.StartInfo = info;
                process.OutputDataReceived += (sender, e) => AppendBounded(output, e.Data);
                process.ErrorDataReceived += (sender, e) => AppendBounded(error, e.Data);
                if (!process.Start()) throw new InvalidOperationException("The bundled Python process could not start.");
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (options.Check && !process.WaitForExit(CheckTimeoutMs))
                {
                    process.Kill();
                    process.WaitForExit();
                    throw new TimeoutException("Studio setup check timed out. No Studio server or window was requested.");
                }
                process.WaitForExit();
                if (output.Length != 0) Console.Out.Write(output.ToString());
                if (error.Length != 0) Console.Error.Write(error.ToString());
                if (process.ExitCode != 0)
                    throw new InvalidOperationException(error.Length == 0
                        ? "Studio could not start. Check its existing settings/local-launch.json and bundled runtime."
                        : error.ToString().Trim());
                if (options.Check && !File.Exists(options.Report))
                    throw new InvalidOperationException("The setup check did not produce its requested diagnostic report.");
                return 0;
            }
        }
        catch (Exception ex)
        {
            string message = ex.Message.Length > 8192 ? ex.Message.Substring(0, 8192) : ex.Message;
            Console.Error.WriteLine(message);
            if (options.Check && options.Report != null && !File.Exists(options.Report))
            {
                try { WriteFailure(options.Report, message); }
                catch (Exception reportError) { Console.Error.WriteLine("Diagnostic report was not written: " + reportError.Message); }
            }
            // Only a normal double-click may show a failure dialog. Checks never do.
            if (args.Length == 0)
                MessageBox.Show(message, "KFPS Livery Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }
    }

    private static void Parse(string[] args, Options options)
    {
        HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i++)
        {
            string key = args[i];
            if (!seen.Add(key)) throw new ArgumentException("Repeated launcher option: " + key);
            if (key == "--check") options.Check = true;
            else if (key == "--report")
            {
                if (++i >= args.Length) throw new ArgumentException("--report needs an absolute output file path.");
                options.Report = args[i];
            }
#if KFPS_STUDIO_WORKSPACE
            else if (key == "--workspace")
            {
                if (++i >= args.Length) throw new ArgumentException("--workspace needs the explicit repo/livery workspace directory.");
                options.Workspace = LocalAbsolute(args[i]);
            }
#endif
            else throw new ArgumentException("Unsupported launcher option: " + key);
        }
        if (options.Check != (options.Report != null))
            throw new ArgumentException("Use --check --report with an absolute, new diagnostic file path.");
    }

    private static string LocalAbsolute(string value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length < 3 || !char.IsLetter(value[0])
            || value[1] != ':' || (value[2] != '\\' && value[2] != '/'))
            throw new ArgumentException("Use an absolute local drive path, not a relative or network path.");
        return Path.GetFullPath(value);
    }

    private static void ValidateReport(string path)
    {
        string full = LocalAbsolute(path);
        string parent = Path.GetDirectoryName(full);
        if (!Directory.Exists(parent)) throw new ArgumentException("The diagnostic report's parent directory must already exist.");
        for (DirectoryInfo directory = new DirectoryInfo(parent); directory != null; directory = directory.Parent)
            if ((directory.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new ArgumentException("The diagnostic report cannot use redirected directories.");
        if (File.Exists(full) || Directory.Exists(full))
            throw new IOException("The diagnostic report already exists; choose a new path. Nothing was overwritten.");
    }

    private static string ResolveRoot(string baseDirectory, string workspace)
    {
        if (workspace != null)
        {
            string repo = Path.Combine(workspace, "repo"), lab = Path.Combine(workspace, "livery");
            if (!Directory.Exists(repo) || !Directory.Exists(lab)
                || !File.Exists(Path.Combine(lab, "src", "launch_studio.py")))
                throw new InvalidOperationException("The explicit development workspace must contain sibling repo and livery directories.");
            return repo;
        }
        string adjacent = Path.GetFullPath(baseDirectory);
        string nested = Path.Combine(adjacent, "KloudysFH6Painter");
        if (Directory.Exists(Path.Combine(nested, "tools", "livery-studio"))) return nested;
        return adjacent;
    }

    private static void WriteFailure(string path, string message)
    {
        ValidateReport(path);
        string json = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
            { "format", ReportFormat }, { "ok", false }, { "check", true },
            { "stage", "windows-launcher" }, { "error", message },
            { "server_started", false }, { "window_opened", false }
        });
        using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false))) writer.WriteLine(json);
    }

    private static void AppendBounded(StringBuilder target, string line)
    {
        if (line == null) return;
        lock (target)
        {
            int remaining = 65536 - target.Length;
            if (remaining > 0) target.AppendLine(line.Length <= remaining ? line : line.Substring(0, remaining));
        }
    }

    private static string Quote(string value)
    {
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            result.Append(c);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }
}
