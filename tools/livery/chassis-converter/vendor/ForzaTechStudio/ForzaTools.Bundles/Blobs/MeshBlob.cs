using Syroot.BinaryData;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Runtime.InteropServices;
using ForzaTools.Bundles.Metadata;

namespace ForzaTools.Bundles.Blobs;

// Mesh blob (tag 'Mesh'). Defines draw call geometry including material, LOD, buffer references, and UV transforms.
// v1.9+ uses a 4-element material ID array; older versions use a single int16.

public class MeshBlob : BundleBlob
{
    public string NameSuffix { get; set; } = "0";

    // v1.13+: explicit material-group count at the start of the blob.
    // The rest of the tooling still treats the first group as the active material binding.
    public List<short[]> MaterialGroups { get; set; } = new();

    // v1.9+ Material IDs array (4 shorts; game uses [1] as the actual material index)
    public short[] MaterialIds { get; set; }
    // Pre-v1.9 single material ID (also synced from MaterialIds[1] when reading v1.9)
    public short MaterialId { get; set; }

    public short RigidBoneIndex { get; set; } = 1;
    public byte LODLevel1 { get; set; } = 0;
    public byte LODLevel2 { get; set; } = 255;
    public ushort LODFlags { get; set; }

    // LODFlags bitfield: bit0=LODS, bits 1-0=LOD0, bits 2-6=LOD1-LOD5.
    public bool LOD_LODS { get => (LODFlags & 1) != 0; set => LODFlags = (ushort)(value ? LODFlags | 1 : LODFlags & ~1); }
    public bool LOD_LOD0 { get => (LODFlags & 3) != 0; set => LODFlags = (ushort)(value ? LODFlags | 3 : LODFlags & ~3); }
    public bool LOD_LOD1 { get => (LODFlags & 4) != 0; set => LODFlags = (ushort)(value ? LODFlags | 4 : LODFlags & ~4); }
    public bool LOD_LOD2 { get => (LODFlags & 8) != 0; set => LODFlags = (ushort)(value ? LODFlags | 8 : LODFlags & ~8); }
    public bool LOD_LOD3 { get => (LODFlags & 16) != 0; set => LODFlags = (ushort)(value ? LODFlags | 16 : LODFlags & ~16); }
    public bool LOD_LOD4 { get => (LODFlags & 32) != 0; set => LODFlags = (ushort)(value ? LODFlags | 32 : LODFlags & ~32); }
    public bool LOD_LOD5 { get => (LODFlags & 64) != 0; set => LODFlags = (ushort)(value ? LODFlags | 64 : LODFlags & ~64); }

    // BucketFlags bits 
    public bool IsOpaque { get; set; }
    public bool IsDecal { get; set; }
    public bool IsTransparent { get; set; }
    public bool IsShadow { get; set; }
    public bool IsNotShadow { get; set; }
    public bool IsAlphaToCoverage { get; set; }

    public byte BucketOrder { get; set; }
    public byte SkinningElementsCount { get; set; }
    public uint MorphTargetCount { get; set; } = 1;
    public uint MorphWeightsCount { get => MorphTargetCount; set => MorphTargetCount = value; }
    public bool IsMorphDamage { get; set; } = true;
    public bool Is32BitIndices { get; set; } = true;
    public ushort Topology { get; set; } = 4;         // D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST = 4
    public int IndexBufferIndex { get; set; }
    public int IndexBufferOffset { get; set; }
    public int IndexBufferDrawOffset { get; set; }
    public int IndexedVertexOffset { get; set; }
    public int IndexCount { get; set; }
    public int PrimCount { get; set; }
    public float ACMR { get; set; } = 0.65f;
    public uint ReferencedVertexCount { get; set; }
    // v1.11+: serialized referenced-vertex list. Older versions synthesize 0..ReferencedVertexCount-1.
    public uint[] ReferencedVertexIndices { get; set; } = Array.Empty<uint>();
    public uint[] PostRefArray { get => ReferencedVertexIndices; set => ReferencedVertexIndices = value ?? Array.Empty<uint>(); }
    public int VertexLayoutIndex { get; set; }
    public List<VertexBufferUsage> VertexBuffers { get; set; } = new();
    public int MorphDataBufferIndex { get; set; }
    public int SkinningDataBufferIndex { get; set; }
    public int[] ConstantBufferIndices { get; set; } = Array.Empty<int>();
    public uint SourceMeshIndex { get; set; }
    public Vector4[] TexCoordTransforms { get; set; }
    public Vector4 PositionScale { get; set; } = Vector4.One;
    public Vector4 PositionTranslate { get; set; }

    // One vertex buffer usage entry in the mesh's VB list.
    // Fields: Index (buffer id), InputSlot (D3D12 slot), Stride (bytes/vertex), Offset.
    // FH6 preserves a 5th dword on v1.12+ wire records, but no downstream consumer has been
    // identified yet, so treat it as reserved-by-wire for now.
    public class VertexBufferUsage
    {
        public int Index { get; set; }
        public uint InputSlot { get; set; }  
        public uint Stride { get; set; }
        public uint Offset { get; set; }
        public uint Reserved { get; set; }
        public uint Unknown { get => Reserved; set => Reserved = value; }
    }

    public override void ReadBlobData(BinaryStream bs)
    {
        int materialGroupCount = IsAtLeastVersion(1, 13) ? bs.ReadInt32() : 1;
        MaterialGroups = new List<short[]>(materialGroupCount);

        for (int i = 0; i < materialGroupCount; i++)
        {
            if (IsAtLeastVersion(1, 9))
                MaterialGroups.Add(bs.ReadInt16s(4));
            else
                MaterialGroups.Add(new short[] { bs.ReadInt16() });
        }

        short[] primaryMaterialGroup = MaterialGroups.Count > 0 ? MaterialGroups[0] : Array.Empty<short>();
        if (IsAtLeastVersion(1, 9))
        {
            MaterialIds = primaryMaterialGroup.Length >= 4 ? primaryMaterialGroup : new short[] { -1, MaterialId, -1, -1 };
            MaterialId = MaterialIds[1]; // sync the legacy field
        }
        else
        {
            MaterialId = primaryMaterialGroup.Length > 0 ? primaryMaterialGroup[0] : (short)0;
        }

        RigidBoneIndex = bs.ReadInt16();

        LODFlags = bs.ReadUInt16();

        LODLevel1 = bs.Read1Byte();  // m_MinLOD
        LODLevel2 = bs.Read1Byte();  // m_MaxLOD

        ushort bucketFlagsRaw = bs.ReadUInt16();
        IsOpaque           = (bucketFlagsRaw & 0x01) != 0;
        IsDecal            = (bucketFlagsRaw & 0x02) != 0;
        IsTransparent      = (bucketFlagsRaw & 0x04) != 0;
        IsShadow           = (bucketFlagsRaw & 0x08) != 0;
        IsNotShadow        = (bucketFlagsRaw & 0x10) != 0;
        IsAlphaToCoverage  = (bucketFlagsRaw & 0x20) != 0;

        // Pre-v1.7 files didn't store shadow bits; force them on to match game's in-memory state
        if (!IsAtLeastVersion(1, 7))
        {
            IsShadow    = true;  // bit 3 (0x08)
            IsNotShadow = true;  // bit 4 (0x10)
        }

        BucketOrder = bs.Read1Byte();

        if (IsAtLeastVersion(1, 2))
        {
            SkinningElementsCount = bs.Read1Byte();
            MorphTargetCount = IsAtLeastVersion(1, 10) ? bs.ReadUInt32() : bs.Read1Byte();
        }
        if (IsAtLeastVersion(1, 3)) IsMorphDamage = bs.ReadBoolean();

        Is32BitIndices = bs.ReadBoolean();

        Topology = bs.ReadUInt16();

        IndexBufferIndex      = bs.ReadInt32();
        IndexBufferOffset     = bs.ReadInt32();  
        IndexBufferDrawOffset = bs.ReadInt32();
        IndexedVertexOffset   = bs.ReadInt32();
        IndexCount            = bs.ReadInt32();  
        PrimCount             = bs.ReadInt32();   

        if (IsAtLeastVersion(1, 6)) { ACMR = bs.ReadSingle(); ReferencedVertexCount = bs.ReadUInt32(); }
        if (IsAtLeastVersion(1, 11))
        {
            uint referencedVertexIndexCount = bs.ReadUInt32();
            ReferencedVertexIndices = new uint[referencedVertexIndexCount];
            for (int i = 0; i < referencedVertexIndexCount; i++)
                ReferencedVertexIndices[i] = bs.ReadUInt32();
        }
        else if (IsAtLeastVersion(1, 6))
        {
            ReferencedVertexIndices = BuildIdentityReferencedVertexIndices();
        }

        VertexLayoutIndex = bs.ReadInt32();

        int vbCount = bs.ReadInt32();
        for (int i = 0; i < vbCount; i++)
        {
            VertexBuffers.Add(new VertexBufferUsage
            {
                Index     = bs.ReadInt32(),
                InputSlot = bs.ReadUInt32(), 
                Stride    = bs.ReadUInt32(),
                Offset    = bs.ReadUInt32(),
                Reserved  = IsAtLeastVersion(1, 12) ? bs.ReadUInt32() : 0
            });
        }

        if (IsAtLeastVersion(1, 4)) { MorphDataBufferIndex = bs.ReadInt32(); SkinningDataBufferIndex = bs.ReadInt32(); }

        int cbCount = bs.ReadInt32();
        ConstantBufferIndices = cbCount > 0 ? bs.ReadInt32s(cbCount) : Array.Empty<int>();

        if (IsAtLeastVersion(1, 1)) SourceMeshIndex = bs.ReadUInt32();

        if (IsAtLeastVersion(1, 5))
            TexCoordTransforms = MemoryMarshal.Cast<byte, Vector4>(bs.ReadBytes(0x10 * 5)).ToArray();

        if (IsAtLeastVersion(1, 8))
        {
            PositionScale     = MemoryMarshal.Read<Vector4>(bs.ReadBytes(0x10));
            PositionTranslate = MemoryMarshal.Read<Vector4>(bs.ReadBytes(0x10));
        }
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        List<short[]> materialGroups = GetSerializedMaterialGroups();
        if (IsAtLeastVersion(1, 13))
            bs.WriteInt32(materialGroups.Count);

        if (IsAtLeastVersion(1, 9))
        {
            foreach (short[] materialGroup in materialGroups)
            {
                if (materialGroup != null && materialGroup.Length >= 4)
                    bs.WriteInt16s(materialGroup);
                else
                    bs.WriteInt16s(new short[] { -1, MaterialId, -1, -1 });
            }
        }
        else
        {
            foreach (short[] materialGroup in materialGroups)
                bs.WriteInt16(materialGroup != null && materialGroup.Length > 0 ? materialGroup[0] : MaterialId);
        }

        bs.WriteInt16(RigidBoneIndex);
        bs.WriteUInt16(LODFlags);
        bs.WriteByte(LODLevel1);
        bs.WriteByte(LODLevel2);

        ushort bucketFlagsRaw = BuildBucketFlags();
        bs.WriteUInt16(bucketFlagsRaw);
        bs.WriteByte(BucketOrder);

        if (IsAtLeastVersion(1, 2))
        {
            bs.WriteByte(SkinningElementsCount);
            if (IsAtLeastVersion(1, 10))
                bs.WriteUInt32(MorphTargetCount);
            else
                bs.WriteByte(checked((byte)MorphTargetCount));
        }
        if (IsAtLeastVersion(1, 3)) bs.WriteBoolean(IsMorphDamage);

        bs.WriteBoolean(Is32BitIndices);
        bs.WriteUInt16(Topology);
        bs.WriteInt32(IndexBufferIndex);
        bs.WriteInt32(IndexBufferOffset);
        bs.WriteInt32(IndexBufferDrawOffset);
        bs.WriteInt32(IndexedVertexOffset);
        bs.WriteInt32(IndexCount);
        bs.WriteInt32(PrimCount);

        if (IsAtLeastVersion(1, 6)) { bs.WriteSingle(ACMR); bs.WriteUInt32(ReferencedVertexCount); }
        if (IsAtLeastVersion(1, 11))
        {
            uint[] referencedVertexIndices = ReferencedVertexIndices ?? Array.Empty<uint>();
            bs.WriteUInt32((uint)referencedVertexIndices.Length);
            foreach (var v in referencedVertexIndices) bs.WriteUInt32(v);
        }

        bs.WriteInt32(VertexLayoutIndex);
        WriteVertexBuffers(bs);

        if (IsAtLeastVersion(1, 4)) { bs.WriteInt32(MorphDataBufferIndex); bs.WriteInt32(SkinningDataBufferIndex); }

        bs.WriteInt32(ConstantBufferIndices.Length);
        bs.WriteInt32s(ConstantBufferIndices);

        if (IsAtLeastVersion(1, 1)) bs.WriteUInt32(SourceMeshIndex);
        if (IsAtLeastVersion(1, 5)) bs.Write(MemoryMarshal.Cast<Vector4, byte>(TexCoordTransforms));
        if (IsAtLeastVersion(1, 8)) { bs.WriteVector4(PositionScale); bs.WriteVector4(PositionTranslate); }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 13))
            bs.WriteInt32(1);

        // 1. Material IDs — v1.9 format: 4 shorts, index [1] is the primary material
        bs.WriteInt16(-1);
        bs.WriteInt16(MaterialId);
        bs.WriteInt16(-1);
        bs.WriteInt16(-1);

        // 2. RigidBoneIndex
        bs.WriteInt16(RigidBoneIndex);

        // 3. LODFlags
        bs.WriteUInt16(LODFlags);

        // 4. LOD level bytes (m_MinLOD, m_MaxLOD) — use actual stored values
        // The LODLevel1/LODLevel2 are set by the caller based on which LOD this mesh represents
        bs.WriteByte(LODLevel1);
        bs.WriteByte(LODLevel2);

        // 5. Bucket Flags
        bs.WriteUInt16(BuildBucketFlags());

        // 6. Bucket Order
        bs.WriteByte(BucketOrder);

        // 7. Skinning/Morph Counts
        bs.WriteByte(SkinningElementsCount);
        if (IsAtLeastVersion(1, 10))
            bs.WriteUInt32(MorphTargetCount);
        else
            bs.WriteByte(checked((byte)MorphTargetCount));

        // 8. IsMorphDamage (always v1.3+ in new files)
        bs.WriteBoolean(IsMorphDamage);

        // 9. Is32BitIndices
        bs.WriteBoolean(Is32BitIndices);

        // 10. Topology (uint16 wire)
        bs.WriteUInt16(Topology);

        // 11. Index buffer fields
        bs.WriteInt32(IndexBufferIndex);
        bs.WriteInt32(IndexBufferOffset);
        bs.WriteInt32(IndexBufferDrawOffset);
        bs.WriteInt32(IndexedVertexOffset);
        bs.WriteInt32(IndexCount);
        bs.WriteInt32(PrimCount);

        // 12. ACMR & ReferencedVertexCount (always v1.6+ in new files)
        bs.WriteSingle(ACMR);
        bs.WriteUInt32(ReferencedVertexCount);

        if (IsAtLeastVersion(1, 11))
        {

            bs.WriteUInt32(0); //temporary placeholder for ReferencedVertexIndices count; will be patched later if needed

        }

        // 13. Vertex Layout Index
        bs.WriteInt32(VertexLayoutIndex);

        // 14. Vertex Buffers
        WriteVertexBuffers(bs);

        // 15. Morph/Skin Buffer Indices (always v1.4+ in new files)
        bs.WriteInt32(MorphDataBufferIndex);
        bs.WriteInt32(SkinningDataBufferIndex);

        // 16. Constant Buffers
        bs.WriteInt32(ConstantBufferIndices.Length);
        if (ConstantBufferIndices.Length > 0)
            bs.WriteInt32s(ConstantBufferIndices);

        // 17. Source Mesh Index (always v1.1+ in new files)
        bs.WriteUInt32(SourceMeshIndex);

        // 18. TexCoord Transforms — 5 × Vector4 (80 bytes, always v1.5+ in new files)
        if (TexCoordTransforms != null && TexCoordTransforms.Length >= 5)
        {
            bs.Write(MemoryMarshal.Cast<Vector4, byte>(TexCoordTransforms));
        }
        else
        {
            // Default: identity UV transform (offset=0, scale=1) per channel
            // Format per channel: { u_offset, u_scale, v_offset, v_scale }
            for (int i = 0; i < 5; i++)
            {
                bs.WriteSingle(0.0f);
                bs.WriteSingle(1.0f);
                bs.WriteSingle(0.0f);
                bs.WriteSingle(1.0f);
            }
        }

        // 19. Position Scale/Translate (always v1.8+ in new files)
        bs.WriteVector4(PositionScale);
        bs.WriteVector4(PositionTranslate);
    }

    // Helpers

    private ushort BuildBucketFlags()
    {
        ushort raw = 0;
        if (IsOpaque)          raw |= 0x01;
        if (IsDecal)           raw |= 0x02;
        if (IsTransparent)     raw |= 0x04;
        if (IsShadow)          raw |= 0x08;
        if (IsNotShadow)       raw |= 0x10;
        if (IsAlphaToCoverage) raw |= 0x20;
        return raw;
    }

    private uint[] BuildIdentityReferencedVertexIndices()
    {
        int count = checked((int)ReferencedVertexCount);
        if (count == 0)
            return Array.Empty<uint>();

        var indices = new uint[count];
        for (int i = 0; i < count; i++)
            indices[i] = (uint)i;

        return indices;
    }

    private List<short[]> GetSerializedMaterialGroups()
    {
        if (MaterialGroups.Count != 0)
            return MaterialGroups;

        if (IsAtLeastVersion(1, 9))
        {
            if (MaterialIds != null && MaterialIds.Length >= 4)
                return new List<short[]> { MaterialIds };

            return new List<short[]> { new short[] { -1, MaterialId, -1, -1 } };
        }

        return new List<short[]> { new short[] { MaterialId } };
    }

    private void WriteVertexBuffers(BinaryStream bs)
    {
        bs.WriteInt32(VertexBuffers.Count);
        foreach (var vb in VertexBuffers)
        {
            bs.WriteInt32(vb.Index);
            bs.WriteUInt32(vb.InputSlot);
            bs.WriteUInt32(vb.Stride);
            bs.WriteUInt32(vb.Offset);
            if (IsAtLeastVersion(1, 12)) bs.WriteUInt32(vb.Reserved);
        }
    }
}
