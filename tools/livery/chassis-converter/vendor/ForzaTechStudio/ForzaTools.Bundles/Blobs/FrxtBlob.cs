using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

/// <summary>
/// FRXT blob (0x54585246)  Purpose TBD; present in shaderbin files from FH6+.
/// Stored as raw bytes until structure is reverse-engineered 
/// </summary>
public class FrxtBlob : BundleBlob
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
