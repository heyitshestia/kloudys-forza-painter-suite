using Syroot.BinaryData;
using System;
using System.Collections.Generic;
using System.Linq;

namespace ForzaTools.Bundles.Blobs;

public class ShaderParameterMappingBlob : BundleBlob
{
    public List<MappingEntry> Mappings { get; set; } = new();

    // Total cbuffer size in bytes: max(effectiveByteOffset) + 16, aligned to 16. CBMP only; zero for TXMP/SPMP.
    public int CbufferByteSize { get; private set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        ushort count = 0;
        if (IsAtLeastVersion(3, 1))
            count = bs.ReadUInt16();
        else
            count = bs.Read1Byte();

        for (int i = 0; i < count; i++)
        {
            var entry = new MappingEntry();

            if (IsAtLeastVersion(2, 0))
            {
                entry.NameHash = bs.ReadUInt32();
                entry.IdOrOffset = bs.ReadUInt16();

                if (IsAtLeastVersion(3, 0))
                    entry.Guid = new Guid(bs.ReadBytes(16));
            }
            else
            {
                entry.Name = bs.ReadString(StringCoding.VariableByteCount);
                entry.IdOrOffset = bs.Read1Byte();
            }

            Mappings.Add(entry);
        }

        // For CBMP blobs v≤1.0: IdOrOffset stores register offsets (float4 units).
        // The engine multiplies by 16 after reading to get byte offsets.
        // We record the scale factor per entry so callers can display the correct byte offset.
        bool isLegacyScale = !IsAtLeastVersion(1, 1); // v≤1.0 uses register units
        foreach (var entry in Mappings)
            entry.IsLegacyRegisterOffset = isLegacyScale;

        // Compute cbuffer total size (engine formula for CBMP):
        // max_effective_byte_offset + 16, aligned up to 16 bytes
        if (Mappings.Count > 0)
        {
            int maxByteOffset = Mappings.Max(e => e.EffectiveByteOffset);
            int raw = maxByteOffset + 16;
            CbufferByteSize = (raw + 15) & ~15; // align to 16
        }
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(3, 1))
            bs.WriteUInt16((ushort)Mappings.Count);
        else
            bs.WriteByte((byte)Mappings.Count);

        foreach (var entry in Mappings)
        {
            if (IsAtLeastVersion(2, 0))
            {
                bs.WriteUInt32(entry.NameHash);
                bs.WriteUInt16((ushort)entry.IdOrOffset);

                if (IsAtLeastVersion(3, 0))
                    bs.WriteBytes(entry.Guid.ToByteArray());
            }
            else
            {
                bs.WriteString(entry.Name, StringCoding.VariableByteCount);
                bs.WriteByte((byte)entry.IdOrOffset);
            }
        }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(3, 1))
            bs.WriteUInt16((ushort)Mappings.Count);
        else
            bs.WriteByte((byte)Mappings.Count);

        foreach (var entry in Mappings)
        {
            if (IsAtLeastVersion(2, 0))
            {
                bs.WriteUInt32(entry.NameHash);
                bs.WriteUInt16((ushort)entry.IdOrOffset);

                if (IsAtLeastVersion(3, 0))
                    bs.WriteBytes(entry.Guid.ToByteArray());
            }
            else
            {
                bs.WriteString(entry.Name ?? "", StringCoding.VariableByteCount);
                bs.WriteByte((byte)entry.IdOrOffset);
            }
        }
    }
}

public class MappingEntry
{
    public string Name { get; set; } // v1.0 only
    public uint NameHash { get; set; } // v2.0+
    public int IdOrOffset { get; set; }
    public Guid Guid { get; set; } // v3.0+

    // True when this entry came from a CBMP blob with version ≤ 1.0.
    // In that case IdOrOffset is in float4 register units and must be multiplied
    // by 16 to obtain the byte offset (matching engine post-read transform).
    public bool IsLegacyRegisterOffset { get; set; }

    // The effective byte offset of this mapping inside the constant buffer.
    // For CBMP v≤1.0: IdOrOffset * 16.  For all other blobs/versions: IdOrOffset.
    public int EffectiveByteOffset => IsLegacyRegisterOffset ? IdOrOffset * 16 : IdOrOffset;
}
