using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

/// <summary>
/// SHUD blob (0x53485544) Shader hint / user-data string pair table.
/// Binary layout (from IDA analysis):
///   uint8   count                  number of string-pair entries
///   For each entry:
///     string  key                  variable-length string (converted to lowercase)
///     string  value                variable-length string (converted to lowercase)
///
/// Used to carry named hint/metadata key-value pairs associated with a shader,
/// e.g. technique names, feature flags, or debug hints. Both key and value
/// strings are lowercased by the runtime loader.
/// </summary>
public class ShudBlob : BundleBlob
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
