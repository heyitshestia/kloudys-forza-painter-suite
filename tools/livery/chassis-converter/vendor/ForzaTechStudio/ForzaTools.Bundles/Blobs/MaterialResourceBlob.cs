using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class MaterialResourceBlob : BundleBlob
{
    public string Path { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        // Template: _7BitString path;
        // _7BitString corresponds to .NET's 7-bit encoded int length + string
        Path = bs.ReadString(StringCoding.VariableByteCount);
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        bs.WriteString(Path, StringCoding.VariableByteCount);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        bs.WriteString(Path ?? "", StringCoding.VariableByteCount);
    }
}