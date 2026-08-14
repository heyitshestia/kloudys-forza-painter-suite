using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

/// <summary>
/// TREV blob (0x56455254) Vertex shader register permutation table.
/// Found in shaderbin files. Contains a register index array and per-permutation
/// register-binding override values used by the shader permutation system.
///
///   uint32  elementCount           number of register entries
///   uint32  registers[count]       base register indices
///   uint32  permutationCount       number of shader permutations (default 1)
///   For each permutation:
///     uint16  permutationIndex
///     uint32  values[count]        per-permutation register binding values
/// </summary>
public class TrevBlob : BundleBlob
{
    public byte[] Data { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        Data = GetContents();
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (Data != null)
            bs.WriteBytes(Data);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (Data != null)
            bs.WriteBytes(Data);
    }
}
