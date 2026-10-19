using System.Buffers.Binary;
using System.Numerics;

namespace Kfps.ChassisConverter;

internal readonly record struct NativeMorphDelta(Vector3 Delta, int WeightIndex);
internal readonly record struct NativeMorphedVertex(Vector3 Position, Vector3 Normal);

// FH6 car_tires_pg vertex shader: decompressed position, then MBuf weighted deltas.
// This evaluates supplied coefficients; it does not infer car fitment or select tires.
internal sealed class NativeMorphData
{
    private const int MaxVectors = 4 * 1024 * 1024;
    private const int WeightSlots = 32;
    private readonly NativeMorphDelta[] vectors;
    public int FirstSourceVertex { get; }
    public int VertexCount { get; }
    public int TargetCount { get; }

    private NativeMorphData(int first, int count, int targets, NativeMorphDelta[] values)
    {
        FirstSourceVertex = first;
        VertexCount = count;
        TargetCount = targets;
        vectors = values;
    }

    public static NativeMorphData Decode(ReadOnlySpan<byte> raw, int format, int stride,
        int subElements, int sourceVertices, int targets, int first, int count, bool isDamage)
    {
        if (isDamage) throw new InvalidDataException("Damage morphs require a separate native shader path.");
        if (format != 10 || targets < 1 || targets > WeightSlots || subElements != targets * 2 || stride != targets * 16)
            throw new InvalidDataException("Unsupported native morph format, count or stride.");
        if (sourceVertices < 1 || first < 0 || count < 1 || (long)first + count > sourceVertices
            || (long)sourceVertices * stride != raw.Length || (long)sourceVertices * subElements > MaxVectors)
            throw new InvalidDataException("Native morph buffer bounds or resource limit exceeded.");

        var values = new NativeMorphDelta[count * subElements];
        for (var i = 0; i < values.Length; i++)
        {
            var at = first * stride + i * 8;
            var x = ReadHalf(raw.Slice(at, 2));
            var y = ReadHalf(raw.Slice(at + 2, 2));
            var z = ReadHalf(raw.Slice(at + 4, 2));
            var weight = ReadHalf(raw.Slice(at + 6, 2));
            if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z)
                || !float.IsFinite(weight) || weight < 0 || weight >= WeightSlots || weight != MathF.Truncate(weight))
                throw new InvalidDataException("Native morph contains nonfinite deltas or invalid weight indices.");
            values[i] = new(new(x, y, z), (int)weight);
        }
        return new(first, count, targets, values);
    }

    private static float ReadHalf(ReadOnlySpan<byte> raw) =>
        (float)BitConverter.UInt16BitsToHalf(BinaryPrimitives.ReadUInt16LittleEndian(raw));

    public NativeMorphDelta Position(int vertex, int target) => At(vertex, target, false);
    public NativeMorphDelta Normal(int vertex, int target) => At(vertex, target, true);

    private NativeMorphDelta At(int vertex, int target, bool normal)
    {
        if ((uint)vertex >= VertexCount || (uint)target >= TargetCount)
            throw new InvalidDataException("Native morph vertex or target is out of range.");
        return vectors[vertex * TargetCount * 2 + target + (normal ? TargetCount : 0)];
    }

    public NativeMorphedVertex ApplyLocal(int vertex, Vector3 decompressedPosition, Vector3 normal,
        ReadOnlySpan<float> weights, float higherSlotModulation)
    {
        if ((uint)vertex >= VertexCount || weights.Length < 1 || weights.Length > WeightSlots
            || !Finite(decompressedPosition) || !Finite(normal) || !float.IsFinite(higherSlotModulation)
            || higherSlotModulation < 0 || higherSlotModulation > 1)
            throw new InvalidDataException("Invalid native morph evaluation input.");
        foreach (var weight in weights)
            if (!float.IsFinite(weight)) throw new InvalidDataException("Native morph weights must be finite.");
        var position = decompressedPosition;
        for (var i = 0; i < TargetCount; i++)
        {
            position += Weighted(Position(vertex, i), weights, higherSlotModulation);
            normal += Weighted(Normal(vertex, i), weights, higherSlotModulation);
        }
        var length = normal.LengthSquared();
        if (!Finite(position) || !Finite(normal) || !float.IsFinite(length) || length <= 1e-20f)
            throw new InvalidDataException("Native morph produced an invalid position or normal.");
        return new(position, normal / MathF.Sqrt(length));
    }

    private static Vector3 Weighted(NativeMorphDelta delta, ReadOnlySpan<float> weights, float modulation)
    {
        if (delta.WeightIndex >= weights.Length)
            throw new InvalidDataException("A native morph coefficient is missing; no default is inferred.");
        var weight = weights[delta.WeightIndex];
        if (delta.WeightIndex > 1) weight *= modulation;
        return delta.Delta * weight;
    }

    private static bool Finite(Vector3 value) => float.IsFinite(value.X) && float.IsFinite(value.Y) && float.IsFinite(value.Z);
}
