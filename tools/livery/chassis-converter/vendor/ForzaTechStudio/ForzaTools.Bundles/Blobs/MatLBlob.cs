using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class MatLBlob : BundleBlob
{
    public string Path { get; set; }
    public string PathV1_1 { get; set; }
    public string PathV1_2 { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        // _7BitString in template = VariableByteCount in Syroot
        Path = bs.ReadString(StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 1))
            PathV1_1 = bs.ReadString(StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 2))
            PathV1_2 = bs.ReadString(StringCoding.VariableByteCount);
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        bs.WriteString(Path, StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 1))
            bs.WriteString(PathV1_1, StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 2))
            bs.WriteString(PathV1_2, StringCoding.VariableByteCount);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        bs.WriteString(Path ?? "", StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 1))
            bs.WriteString(PathV1_1 ?? "", StringCoding.VariableByteCount);

        if (IsAtLeastVersion(1, 2))
            bs.WriteString(PathV1_2 ?? "", StringCoding.VariableByteCount);
    }
}