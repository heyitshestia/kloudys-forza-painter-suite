using System.Reflection;
using ForzaTools.CarScene;

namespace Kfps.ChassisConverter;

internal static class ConverterTests
{
    private static int Main()
    {
        var method = typeof(Program).GetMethod("NativeAllowedSides", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new Exception("Native mask policy missing.");
        var cases = 0;
        var failures = new List<string>();
        void Check(string role, string mesh, CCarParts part, bool uv3, int valid, int expected)
        {
            cases++;
            var actual = (int)method.Invoke(null, [role, mesh, part, uv3, valid]);
            if (actual != expected) failures.Add($"{role}/{mesh}/{part}/uv3={uv3}/mask={valid}: expected {expected}, got {actual}");
        }

        // Mesh and part names describe assemblies, not native section ownership.
        foreach (var part in Enum.GetValues<CCarParts>())
        foreach (var name in new[] { "trunk_a_LODS0", "trunkBay_a_LODS", "spoiler_a", "wing_a", "hood_a", "body_a", "doorRF_a" })
        {
            Check("paint", name, part, true, 1791, 63);
            Check("paint", name, part, true, 16, 16);
            Check("paint", name, part, true, 32, 32);
            Check("paint", name, part, true, 0x7C0, 0);
            Check("paint", name, part, false, 2047, 0);
            Check("paint", name, part, true, 0, 0);
            Check("glass", name, part, true, 2047, 0x7C0);
            Check("glass", name, part, true, 63, 0);
            Check("glass", name, part, false, 2047, 0);
            foreach (var role in new[] { "trim", "hidden", "dark", "" })
                Check(role, name, part, true, 2047, 0);
        }
        Console.WriteLine($"Native surface policy: {cases} checks; {failures.Count} failures.");
        foreach (var failure in failures.Take(12)) Console.WriteLine(failure);
        return failures.Count == 0 ? 0 : 1;
    }
}
