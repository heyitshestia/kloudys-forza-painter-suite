using Syroot.BinaryData;
using System.Collections.Generic;

namespace ForzaTools.Bundles.Metadata;

public class VDCLMetadata : BundleMetadata
{
    public List<VDCLEntry> Entries { get; set; } = new();

    public override void ReadMetadataData(BinaryStream bs)
    {
        if (Version >= 2)
        {

            // Version 2: outerCount = 1 (hardcoded), then per-outer: read innerCount(int32), then innerCount*(nameHash+flags)
            // Version 3: read outerCount(int32), then per-outer: read innerCount(int32), then innerCount*(nameHash+flags)
            // Version 4+: same as v3 but also read a uint16 permutation index per outer iteration
            int outerCount = 1;
            if (Version >= 3)
                outerCount = bs.ReadInt32();

            for (int o = 0; o < outerCount; o++)
            {
                if (Version >= 4)
                    bs.ReadUInt16(); // permutation index (unused by VLay patch)

                int innerCount = bs.ReadInt32();
                for (int i = 0; i < innerCount; i++)
                {
                    Entries.Add(new VDCLEntry
                    {
                        NameHash = bs.ReadUInt32(),
                        VertexInputFlags = (uint)bs.ReadInt32()
                    });
                }
            }
        }
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        if (Version >= 2)
        {
            if (Version >= 3)
                bs.WriteInt32(Entries.Count); // outerCount = total entries (1 entry per outer group)

            // Always write innerCount = number of entries (or 1 group per outer with all entries if v3+)
            // For simplicity, we write all entries in a single inner group.
            bs.WriteInt32(Entries.Count); // innerCount

            foreach (var entry in Entries)
            {
                bs.WriteUInt32(entry.NameHash);
                bs.WriteInt32((int)entry.VertexInputFlags);
            }
        }
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        if (Version >= 2)
        {
            var safeEntries = Entries ?? new List<VDCLEntry>();

            if (Version >= 3)
                bs.WriteInt32(safeEntries.Count); // outerCount

            bs.WriteInt32(safeEntries.Count); // innerCount

            foreach (var entry in safeEntries)
            {
                bs.WriteUInt32(entry.NameHash);
                bs.WriteInt32((int)entry.VertexInputFlags);
            }
        }
    }
}

public class VDCLEntry
{
    public uint NameHash { get; set; }
    //  bitfield of required vertex semantics
    // Bit 0=TEXCOORD0, 1=TEXCOORD1, ... 4=TEXCOORD4, 5=TEXCOORD5/TANGENT0,
    // 6=TANGENT1, 7=TANGENT2, 8=TANGENT3, 9=TANGENT4, 10=COLOR0.
    public uint VertexInputFlags { get; set; }
}
