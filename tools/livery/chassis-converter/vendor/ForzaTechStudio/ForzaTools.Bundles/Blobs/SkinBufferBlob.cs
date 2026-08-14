using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class SkinBufferBlob : BundleBlob
{
    public BufferHeader Header { get; set; } = new();

    public override void ReadBlobData(BinaryStream bs)
    {
        Header.Read(bs, VersionMajor, VersionMinor);
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        Header.Serialize(bs, VersionMajor, VersionMinor);
    }

    // In IndexBufferBlob, VertexBufferBlob, MorphBufferBlob, SkinBufferBlob
    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        Header.CreateModelBin(bs, VersionMajor, VersionMinor);
    }
}