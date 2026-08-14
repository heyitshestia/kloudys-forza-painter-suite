using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Numerics;
using System.Runtime.InteropServices;

using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class BoundaryBoxMetadata : BundleMetadata
{
    public Vector3 Min { get; set; }
    public Vector3 Max { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        Min = MemoryMarshal.Read<Vector3>(bs.ReadBytes(0x0C));
        Max = MemoryMarshal.Read<Vector3>(bs.ReadBytes(0x0C));
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        bs.WriteSingle(Min.X); bs.WriteSingle(Min.Y); bs.WriteSingle(Min.Z);
        bs.WriteSingle(Max.X); bs.WriteSingle(Max.Y); bs.WriteSingle(Max.Z);
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        bs.WriteSingle(Min.X); bs.WriteSingle(Min.Y); bs.WriteSingle(Min.Z);
        bs.WriteSingle(Max.X); bs.WriteSingle(Max.Y); bs.WriteSingle(Max.Z);
    }
}
