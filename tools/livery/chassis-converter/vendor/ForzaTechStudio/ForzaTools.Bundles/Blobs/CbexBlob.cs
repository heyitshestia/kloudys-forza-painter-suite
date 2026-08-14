using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

/// <summary>
/// CBEX blob (0x43424558) Constant Buffer EXtended register data.
/// Found in shaderbin files alongside CBMP blobs. Processed by
/// Purpose: Provides extra register slot information used to calculate the
/// total aligned constant-buffer size (with CBMP as the base layout).
/// The blob contains a small stream read with a max count of 2 entries.
/// Exact layout is preserved as raw bytes pending further analysis.
/// </summary>
public class CbexBlob : BundleBlob
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
