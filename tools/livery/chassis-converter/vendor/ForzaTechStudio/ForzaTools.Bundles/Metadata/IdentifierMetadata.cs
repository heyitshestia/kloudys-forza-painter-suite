using Syroot.BinaryData;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ForzaTools.Bundles.Metadata;

public class IdentifierMetadata : BundleMetadata
{
    public uint Id { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        Id = bs.ReadUInt32();
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        bs.WriteUInt32(Id);
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        bs.WriteUInt32(Id);
    }
}
