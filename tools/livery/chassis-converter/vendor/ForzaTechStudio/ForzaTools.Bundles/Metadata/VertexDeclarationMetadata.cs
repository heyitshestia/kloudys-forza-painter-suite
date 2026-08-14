using Syroot.BinaryData;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ForzaTools.Bundles.Metadata
{
    public class VertexDeclarationMetadata : BundleMetadata
    {
        public int UnkV2_Size { get; private set; }

        public class UnkV2Entry
        {
            public uint Unk1 { get; set; } // unsigned long
            public uint Unk2 { get; set; } // unsigned long

            public UnkV2Entry(uint unk1, uint unk2)
            {
                Unk1 = unk1;
                Unk2 = unk2;
            }
        }

        public List<UnkV2Entry> UnkV2 { get; private set; } = new List<UnkV2Entry>();

        public override void ReadMetadataData(BinaryStream bs)
        {
            if (Version >= 2)
            {
                // Read the size
                UnkV2_Size = bs.ReadInt32();

                // Read the array of entries
                for (int i = 0; i < UnkV2_Size; i++)
                {
                    uint unk1 = bs.ReadUInt32();
                    uint unk2 = bs.ReadUInt32();
                    UnkV2.Add(new UnkV2Entry(unk1, unk2));
                }
            }
        }

        public override void SerializeMetadataData(BinaryStream bs)
        {
            if (Version >= 2)
            {
                // Write the size
                bs.WriteInt32(UnkV2_Size);

                // Write the array of entries
                foreach (var entry in UnkV2)
                {
                    bs.WriteUInt32(entry.Unk1);
                    bs.WriteUInt32(entry.Unk2);
                }
            }
        }

        public override void CreateModelBinMetadataData(BinaryStream bs)
        {
            if (Version >= 2)
            {
                // Write the size
                bs.WriteInt32(UnkV2_Size);

                // Write the array of entries
                foreach (var entry in UnkV2)
                {
                    bs.WriteUInt32(entry.Unk1);
                    bs.WriteUInt32(entry.Unk2);
                }
            }
        }
    }
}
