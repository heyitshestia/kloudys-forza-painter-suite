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
#if KFPS_EDITOR
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool AllowSetForegroundWindow(uint processId);

    private static readonly string EntryPoint = Path.Combine("KFPS.Editor", "editor.py");
    private static readonly string Requirements = Path.Combine("KFPS.Editor", "requirements.txt");
#else
    private static readonly string EntryPoint = Path.Combine("KFPS.UI", "app.py");
    private const string Requirements = "requirements.txt";
#endif
    private const string PythonProbe =
        "import struct,sys;" +
        "assert sys.version_info[:2] == (3, 12), sys.version;" +
        "assert struct.calcsize('P') == 8, 'KFPS requires 64-bit Python';" +
#if KFPS_EDITOR
        "import PySide6.QtWebEngineWidgets,psutil,win32api,win32file,PIL,numpy";
#else
        "import PySide6,psutil,win32api,PIL,numpy,cv2";
#endif

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
            string app = ResolveEntryPoint(appRoot);

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
#if KFPS_EDITOR
                bool korean = System.Globalization.CultureInfo.CurrentUICulture.Name.StartsWith("ko", StringComparison.OrdinalIgnoreCase);
                MessageBox.Show(korean
                    ? "에디터의 전용 실행 환경이 없거나 손상되었습니다. KFPS를 닫고 KFPS-Updater.exe를 실행한 다음 에디터를 다시 열어 주세요. 프로젝트와 설정은 유지됩니다."
                    : "The editor's bundled runtime is missing. Close KFPS and run KFPS-Updater.exe, then reopen the editor. Your projects and settings will be kept.",
                    "KFPS Editor", MessageBoxButtons.OK, MessageBoxIcon.Error);
#else
                string requirements = Path.Combine(appRoot, Requirements);
                MessageBox.Show(
                    "KFPS could not find a compatible Python installation.\n\n" +
                    "Use the bundled KFPS package, or close KFPS and run KFPS-Updater.exe to repair its runtime. The advanced no-Python download is retired.\n\n" +
                    "For source development only:\n" +
                    "Install Python 3.12, then run:\n" +
                    "py -3.12 -m pip install -r " + Quote(requirements) + "\n\n" +
                    "If Python is installed in a custom location, set KFPS_PYTHON to its python.exe path. " +
                    "The bundled KFPS release does not require a system Python installation.",
                    "KFPS launch failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
#endif
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
#if KFPS_EDITOR
            if (!IsDevelopmentRoot(appRoot))
            {
                foreach (string key in info.EnvironmentVariables.Keys.Cast<string>().ToArray())
                {
                    string upper = key.ToUpperInvariant();
                    if (upper.StartsWith("PYTHON") || upper.StartsWith("QT_") || upper.StartsWith("QTWEBENGINE")
                        || upper.StartsWith("QML") || upper.StartsWith("PYSIDE") || upper.StartsWith("SHIBOKEN"))
                        info.EnvironmentVariables.Remove(key);
                }
                info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
                info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            }
#endif
            using (Process process = Process.Start(info))
            {
                if (process == null)
                {
                    return 3;
                }
#if KFPS_EDITOR
                if (!args.Contains("--background"))
                    AllowSetForegroundWindow((uint)process.Id);
#endif
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
            return new PythonLaunch(bundledWindowed, BundledArguments(appRoot), "bundled");
        }

        string bundledConsole = Path.Combine(appRoot, "python", "python.exe");
        if (File.Exists(bundledConsole))
        {
            return new PythonLaunch(bundledConsole, BundledArguments(appRoot), "bundled");
        }
#if KFPS_EDITOR
        if (!IsDevelopmentRoot(appRoot)) return null;
#endif

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

    private static string BundledArguments(string appRoot)
    {
#if KFPS_EDITOR
        return IsDevelopmentRoot(appRoot) ? "" : "-I -B -X " + Quote("pycache_prefix=" +
            Path.Combine(appRoot, "runtime", "fabric-editor", ".bytecode-" + Guid.NewGuid().ToString("N")));
#else
        return "";
#endif
    }

    private static bool IsDevelopmentRoot(string appRoot)
    {
        if (File.Exists(Path.Combine(appRoot, "KFPS.Editor", "baseline.json"))) return false;
        if (Directory.Exists(Path.Combine(appRoot, ".git")) || File.Exists(Path.Combine(appRoot, ".git"))) return true;
        if (!File.Exists(Path.Combine(appRoot, "editor-stage.json"))) return false;
        DirectoryInfo parent = Directory.GetParent(Path.GetFullPath(appRoot));
        while (parent != null)
        {
            if (parent.Name == "test-runs" && parent.Parent != null && parent.Parent.Name == "runtime")
            {
                string root = parent.Parent.Parent.FullName;
                return Directory.Exists(Path.Combine(root, ".git")) || File.Exists(Path.Combine(root, ".git"));
            }
            parent = parent.Parent;
        }
        return false;
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
            && File.Exists(ResolveEntryPoint(path));
    }

    private static string ResolveEntryPoint(string path)
    {
        string entry = Path.Combine(path, EntryPoint);
        return entry;
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
