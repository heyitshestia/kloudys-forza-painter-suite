using Syroot.BinaryData;
using static System.Runtime.InteropServices.JavaScript.JSType;

namespace ForzaTools.Bundles.Blobs;

public class VersBlob : BundleBlob
{
    public uint Unk { get; set; }
    public string Path { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        Unk = bs.ReadUInt32();
        Path = bs.ReadString(StringCoding.VariableByteCount);
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        bs.WriteUInt32(Unk);
        bs.WriteString(Path, StringCoding.VariableByteCount);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        bs.WriteUInt32(Unk);
        bs.WriteString(Path, StringCoding.VariableByteCount);
    }
}

public class VarsBlob : BundleBlob
{
    // Implementation based on template comments (mostly unknown/placeholder)
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