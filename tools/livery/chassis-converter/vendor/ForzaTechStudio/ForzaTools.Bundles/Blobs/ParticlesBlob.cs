using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class ParticleBlob : BundleBlob
{
    public byte[] Data { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        Data = GetContents(); // Uses the base class _data
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