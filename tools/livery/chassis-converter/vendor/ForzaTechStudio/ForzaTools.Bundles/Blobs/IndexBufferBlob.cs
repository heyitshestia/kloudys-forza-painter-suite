using Syroot.BinaryData;
using ForzaTools.Bundles.Metadata;

namespace ForzaTools.Bundles.Blobs;

public class IndexBufferBlob : BundleBlob
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

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        // Delegates to Header.CreateModelBin so index edits are preserved
        Header.CreateModelBin(bs, VersionMajor, VersionMinor);
    }
}