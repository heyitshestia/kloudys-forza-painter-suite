using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

/// <summary>
/// PARM blob (0x5041524D) Shader parameter name/ID mapping table.
/// Found in shaderbin files. 
/// Binary layout:
///   uint32  count                  number of parameter entries
///   For each entry:
///     uint32  paramId              parameter index / hash ID
///     string  paramName            variable-length string name
///     [if blob version >= 1.2]:
///       uint32  paramValue         additional integer value
///       string  paramValue2        additional string (only if non-empty)
///
/// Used by the shader permutation system to map parameter IDs to named slots
/// in the a1+600 and a1+664 parameter tables of the material system object.
/// </summary>
public class ParmBlob : BundleBlob
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
