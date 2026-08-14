using Syroot.BinaryData;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ForzaTools.Bundles.Metadata;

public class NameMetadata : BundleMetadata
{
    public string Name { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        Name = bs.ReadString(Size);
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        bs.WriteString(Name, StringCoding.Raw);
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        bs.WriteString(Name ?? "", StringCoding.Raw);
    }
}
