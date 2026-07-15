using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Forms;

internal static class KfpsLauncher
{
    private const int PythonProbeTimeoutMs = 15000;
    private const string PythonProbe =
        "import struct,sys;" +
        "assert sys.version_info[:2] == (3, 12), sys.version;" +
        "assert struct.calcsize('P') == 8, 'KFPS requires 64-bit Python';" +
        "import PySide6,psutil,win32api,PIL,numpy,cv2";

    private sealed class PythonLaunch
    {
        internal PythonLaunch(string fileName, string prefixArguments, string source)
        {
            FileName = fileName;
            PrefixArguments = prefixArguments;
            Source = source;
        }

        internal string FileName { get; private set; }
        internal string PrefixArguments { get; private set; }
        internal string Source { get; private set; }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string appRoot = ResolveAppRoot(baseDir);
            string app = Path.Combine(appRoot, "KFPS.UI", "app.py");

            if (!File.Exists(app))
            {
                MessageBox.Show(
                    "KFPS could not find its UI files.\n\n" +
                    "Keep KFPS.exe beside the complete KloudysFH6Painter folder. " +
                    "GitHub source downloads are not runnable release packages.",
                    "KFPS launch failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 2;
            }

            PythonLaunch python = ResolvePython(appRoot);
            if (python == null)
            {
                string requirements = Path.Combine(appRoot, "requirements.txt");
                MessageBox.Show(
                    "KFPS could not find a compatible Python installation.\n\n" +
                    "The no-Python release requires 64-bit Python 3.12 with the KFPS dependencies installed.\n\n" +
                    "Install Python 3.12, then run:\n" +
                    "py -3.12 -m pip install -r " + Quote(requirements) + "\n\n" +
                    "If Python is installed in a custom location, set KFPS_PYTHON to its python.exe path. " +
                    "The bundled KFPS release does not require a system Python installation.",
                    "KFPS launch failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 2;
            }

            string arguments = JoinArguments(python.PrefixArguments, Quote(app));
            if (args.Length > 0)
            {
                arguments = JoinArguments(arguments, string.Join(" ", args.Select(Quote)));
            }

            ProcessStartInfo info = new ProcessStartInfo
            {
                FileName = python.FileName,
                Arguments = arguments,
                WorkingDirectory = appRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            info.EnvironmentVariables["KFPS_APP_ROOT"] = appRoot;
            info.EnvironmentVariables["KFPS_PYTHON_SOURCE"] = python.Source;
            using (Process process = Process.Start(info))
            {
                if (process == null)
                {
                    return 3;
                }
                if (args.Length > 0)
                {
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "KFPS launch failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static PythonLaunch ResolvePython(string appRoot)
    {
        string bundledWindowed = Path.Combine(appRoot, "python", "pythonw.exe");
        if (File.Exists(bundledWindowed))
        {
            return new PythonLaunch(bundledWindowed, "", "bundled");
        }

        string bundledConsole = Path.Combine(appRoot, "python", "python.exe");
        if (File.Exists(bundledConsole))
        {
            return new PythonLaunch(bundledConsole, "", "bundled");
        }

        string configured = NormalizePythonPath(Environment.GetEnvironmentVariable("KFPS_PYTHON"));
        if (ProbePython(configured, ""))
        {
            return new PythonLaunch(configured, "", "KFPS_PYTHON");
        }

        foreach (string launcher in PythonLauncherCandidates())
        {
            if (ProbePython(launcher, "-3.12"))
            {
                return new PythonLaunch(launcher, "-3.12", "py -3.12");
            }
        }

        foreach (string candidate in SystemPythonCandidates())
        {
            if (ProbePython(candidate, ""))
            {
                return new PythonLaunch(candidate, "", "system Python 3.12");
            }
        }

        return null;
    }

    private static IEnumerable<string> PythonLauncherCandidates()
    {
        HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        foreach (string candidate in new[]
        {
            Path.Combine(windows, "py.exe"),
            FindOnPath("py.exe"),
        })
        {
            if (!string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate) && seen.Add(candidate))
            {
                yield return candidate;
            }
        }
    }

    private static IEnumerable<string> SystemPythonCandidates()
    {
        HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        List<string> candidates = new List<string>();
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);

        candidates.Add(Path.Combine(local, "Programs", "Python", "Python312", "python.exe"));
        candidates.Add(Path.Combine(programFiles, "Python312", "python.exe"));
        candidates.Add(Path.Combine(programFiles, "Python 3.12", "python.exe"));
        candidates.Add(Path.Combine(programFilesX86, "Python312", "python.exe"));

        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string entry in path.Split(Path.PathSeparator))
        {
            string directory = entry.Trim().Trim('"');
            if (directory.Length > 0)
            {
                candidates.Add(Path.Combine(directory, "python.exe"));
                candidates.Add(Path.Combine(directory, "python3.12.exe"));
            }
        }

        foreach (string rawCandidate in candidates)
        {
            string candidate = NormalizePythonPath(rawCandidate);
            if (!string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate) && seen.Add(candidate))
            {
                yield return candidate;
            }
        }
    }

    private static string NormalizePythonPath(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        try
        {
            string candidate = Environment.ExpandEnvironmentVariables(value.Trim().Trim('"'));
            if (Directory.Exists(candidate))
            {
                candidate = Path.Combine(candidate, "python.exe");
            }
            if (string.Equals(Path.GetFileName(candidate), "pythonw.exe", StringComparison.OrdinalIgnoreCase))
            {
                string console = Path.Combine(Path.GetDirectoryName(candidate) ?? "", "python.exe");
                if (File.Exists(console))
                {
                    candidate = console;
                }
            }
            return Path.GetFullPath(candidate);
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static bool ProbePython(string executable, string prefixArguments)
    {
        if (string.IsNullOrWhiteSpace(executable) || !File.Exists(executable))
        {
            return false;
        }

        try
        {
            ProcessStartInfo info = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = JoinArguments(prefixArguments, "-c", Quote(PythonProbe)),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using (Process process = Process.Start(info))
            {
                if (process == null)
                {
                    return false;
                }
                if (!process.WaitForExit(PythonProbeTimeoutMs))
                {
                    try
                    {
                        process.Kill();
                    }
                    catch (Exception)
                    {
                    }
                    return false;
                }
                return process.ExitCode == 0;
            }
        }
        catch (Exception)
        {
            return false;
        }
    }

    private static string FindOnPath(string fileName)
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string entry in path.Split(Path.PathSeparator))
        {
            string directory = entry.Trim().Trim('"');
            if (directory.Length == 0)
            {
                continue;
            }
            string candidate = Path.Combine(directory, fileName);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }
        return null;
    }

    private static string ResolveAppRoot(string baseDir)
    {
        string nested = Path.Combine(baseDir, "KloudysFH6Painter");
        if (LooksLikeAppRoot(nested))
        {
            return nested;
        }
        if (LooksLikeAppRoot(baseDir))
        {
            return baseDir;
        }
        return nested;
    }

    private static bool LooksLikeAppRoot(string path)
    {
        return Directory.Exists(path)
            && File.Exists(Path.Combine(path, "VERSION"))
            && File.Exists(Path.Combine(path, "KFPS.UI", "app.py"));
    }

    private static string JoinArguments(params string[] parts)
    {
        return string.Join(" ", parts.Where(part => !string.IsNullOrWhiteSpace(part)));
    }

    private static string Quote(string value)
    {
        if (value == null)
        {
            return "\"\"";
        }
        StringBuilder builder = new StringBuilder();
        builder.Append('"');
        int backslashes = 0;
        foreach (char c in value)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }
            if (c == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
                continue;
            }
            builder.Append('\\', backslashes);
            backslashes = 0;
            builder.Append(c);
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }
}
