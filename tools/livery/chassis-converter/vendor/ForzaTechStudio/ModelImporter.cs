using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Text;
using System.Buffers.Binary;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;

namespace ForzaTechStudio.Services
{
    public sealed class ForzaGeometryData
    {
        public string Name;
        public string MaterialName; 

        // Render Data
        public Vector3[] Positions;
        public Vector3[] Normals;
        public Vector2[] UVs;
        public Dictionary<int, Vector2[]> UvChannels;
        public Vector4[] Colors;
        public int[] Indices;

        // PRE-CALCULATED FOR RENDERING SPEED
        public Vector3[] InitialRenderPositions;

        // EDITING SUPPORT
        public MeshBlob SourceMesh;
        public Vector3[] RawPositions; // Normalized -1..1 values (before Scale/Translate)
        public int MinVertexIndex; // lowest source vertex id; needed to write edits back
        public Matrix4x4 BoneTransform;
        
        // BONE TRACKING (for inverse transform calculations)
        public short BoneIndex { get; set; } = -1;
        public string BoneName { get; set; } = string.Empty;
        public Matrix4x4 OriginalBoneTransform { get; set; } = Matrix4x4.Identity;
        
        // NEW: Direct reference to bone object for editing
        public Bone SourceBone { get; set; }
        
        // NEW: Track original mesh translate relative to bone
        public Vector4 OriginalMeshTranslateRelativeToBone { get; set; } = Vector4.Zero;

        // Damage model (morph buffer at weight=1.0)
        public Vector3[] DamageRawPositions;
        public bool HasDamageModel => DamageRawPositions != null;

        // Rotation (Euler angles in degrees, applied after Scale before Translate)
        public Vector3 RotationEulerDegrees { get; set; } = Vector3.Zero;
        
        // Builds a rotation Matrix4x4 from the current Euler angles (XYZ order).
        public Matrix4x4 GetRotationMatrix()
        {
            if (RotationEulerDegrees == Vector3.Zero) return Matrix4x4.Identity;
            float rx = RotationEulerDegrees.X * MathF.PI / 180f;
            float ry = RotationEulerDegrees.Y * MathF.PI / 180f;
            float rz = RotationEulerDegrees.Z * MathF.PI / 180f;
            // RotX box rotates around the Y-axis (visually spins the X-axis facing side).
            // RotY box rotates around the X-axis (visually tilts the Y-axis facing side).
            return Matrix4x4.CreateRotationY(rx) * Matrix4x4.CreateRotationX(ry) * Matrix4x4.CreateRotationZ(rz);
        }
    }

    public sealed class ImporterResult
    {
        public readonly List<ForzaGeometryData> Meshes = new();
        public readonly List<string> Logs = new();
    }

    public sealed class ModelImporter
    {
        private readonly List<string> _logs = new();
        private void Log(string s) => _logs.Add(s);

        private const int MODEL_BUFFER_HEADER_SIZE = 16;

        private class ElementInfo
        {
            public D3D12_INPUT_LAYOUT_DESC Desc;
            public int Offset;
        }

        public ImporterResult ExtractModels(Bundle bundle)
        {
            var result = new ImporterResult();
            _logs.Clear();

            var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();

            // Map Layouts
            var layouts = bundle.Blobs.OfType<VertexLayoutBlob>().ToArray();

            var indexBuffers = bundle.Blobs.OfType<IndexBufferBlob>().ToArray();
            var meshes = bundle.Blobs.OfType<MeshBlob>().ToArray();

            // Build Vertex Buffer Map (Key: Metadata ID)
            var vertexBufferMap = new Dictionary<int, VertexBufferBlob>();
            foreach (var vb in bundle.Blobs.OfType<VertexBufferBlob>())
            {
                var idMeta = vb.Metadatas.OfType<IdentifierMetadata>().FirstOrDefault();
                if (idMeta != null)
                {
                    // Cast to int to match usage keys
                    vertexBufferMap[(int)idMeta.Id] = vb;
                }
            }

            if (indexBuffers.Length == 0) return result;

            // Use the first index buffer (Standard Forza logic)
            var globalIndexBuffer = indexBuffers[0];

            // Handle Index Buffer Data Source (In-Memory vs Loaded)
            byte[] globalIndexData;
            int indexBufferOffset = 0;

            if (globalIndexBuffer.Header?.GetRawData() != null && globalIndexBuffer.Header.GetRawData().Length > 0)
            {
                // In-Memory (No Header in Data) — use raw contiguous buffer directly
                globalIndexData = globalIndexBuffer.Header.GetRawData();
                indexBufferOffset = 0;
            }
            else
            {
                // Loaded (Header included in Data)
                globalIndexData = globalIndexBuffer.GetContents();
                indexBufferOffset = MODEL_BUFFER_HEADER_SIZE;
            }

            Matrix4x4[] boneMatrices = null;
            if (skeleton != null)
            {
                boneMatrices = new Matrix4x4[skeleton.Bones.Count];
                for (int i = 0; i < skeleton.Bones.Count; i++)
                {
                    var b = skeleton.Bones[i];
                    var m = b.Matrix;
                    if (b.ParentId >= 0 && b.ParentId < i) m = m * boneMatrices[b.ParentId];
                    boneMatrices[i] = m;
                }
            }

            var morphBlobs = bundle.Blobs.OfType<MorphBufferBlob>().ToArray();

            foreach (var mesh in meshes)
            {
                // Filter LODs if necessary
              //  if ((mesh.LODFlags & 0b1111) == 0 && !mesh.LOD_LOD0) continue;

                try
                {
                    // Pass 'bundle' and correct offsets
                    var geo = ExtractMesh(bundle, mesh, layouts, vertexBufferMap, globalIndexData, indexBufferOffset, boneMatrices);
                    if (geo != null)
                    {
                        // Decode damage morph buffer if mesh has a morph target
                        if (mesh.IsMorphDamage && mesh.MorphDataBufferIndex >= 0 && geo.RawPositions != null)
                        {
                            MorphBufferBlob morphBlob = null;
                            // Try metadata ID match first
                            foreach (var mb in morphBlobs)
                            {
                                var idMeta = mb.Metadatas.OfType<IdentifierMetadata>().FirstOrDefault();
                                if (idMeta != null && (int)idMeta.Id == mesh.MorphDataBufferIndex)
                                {
                                    morphBlob = mb;
                                    break;
                                }
                            }
                            // Fallback: ordinal index into morph blob array
                            if (morphBlob == null && mesh.MorphDataBufferIndex < morphBlobs.Length)
                                morphBlob = morphBlobs[mesh.MorphDataBufferIndex];

                            if (morphBlob != null)
                                geo.DamageRawPositions = DecodeMorphDeltas(morphBlob, geo.RawPositions, mesh);
                        }
                        result.Meshes.Add(geo);
                    }
                }
                catch (Exception ex) { Log($"Mesh failed: {ex.Message}"); throw; }
            }

            result.Logs.AddRange(_logs);
            return result;
        }

        private ForzaGeometryData ExtractMesh(
            Bundle bundle,
            MeshBlob mesh,
            VertexLayoutBlob[] layouts,
            Dictionary<int, VertexBufferBlob> vbMap,
            byte[] globalIndexData,
            int globalIndexBaseOffset,
            Matrix4x4[] boneMatrices)
        {
            // Resolve Layout
            VertexLayoutBlob layout = null;

            // 1. Try Metadata ID
            var layoutById = bundle.Blobs.OfType<VertexLayoutBlob>()
                .FirstOrDefault(l => l.Metadatas.OfType<IdentifierMetadata>().Any(m => (int)m.Id == mesh.VertexLayoutIndex));

            if (layoutById != null)
                layout = layoutById;
            // 2. Fallback to Array Index
            else if (mesh.VertexLayoutIndex >= 0 && mesh.VertexLayoutIndex < layouts.Length)
                layout = layouts[mesh.VertexLayoutIndex];
            // 3. Last Resort
            else if (layouts.Length > 0)
                layout = layouts[0];

            if (layout == null) throw new Exception("Vertex Layout not found.");

            string name = mesh.Metadatas.OfType<NameMetadata>().FirstOrDefault()?.Name ?? "Mesh";

            // Resolve Material Name
            string matName = "Unknown";
            short matId = mesh.MaterialId;
            // Handle v1.9 array
            if (mesh.MaterialIds != null && mesh.MaterialIds.Length > 1) matId = mesh.MaterialIds[1];
            
            var matBlob = bundle.Blobs.FirstOrDefault(b => b.Metadatas.OfType<IdentifierMetadata>().Any(m => (int)m.Id == matId));
            if (matBlob != null)
            {
                var nameMeta = matBlob.Metadatas.OfType<NameMetadata>().FirstOrDefault();
                if (nameMeta != null) matName = nameMeta.Name;
            }

            // 1. INDICES
            int indexStride = mesh.Is32BitIndices ? 4 : 2;
            int indexCount = mesh.IndexCount;
            
            // FIX: IndexBufferDrawOffset is in INDICES (StartIndexLocation), so multiply by stride
            // Also include IndexBufferOffset as it is used for the base view offset (in BYTES)
            long startIndexOffset = globalIndexBaseOffset + mesh.IndexBufferOffset + (mesh.IndexBufferDrawOffset * indexStride);

            if (globalIndexData == null || startIndexOffset + (indexCount * indexStride) > globalIndexData.Length)
                throw new Exception("Index buffer data out of bounds or missing.");

            var indices = new int[indexCount];
            int minIndex = int.MaxValue;
            int maxIndex = int.MinValue;

            // USE SPAN for Indices
            ReadOnlySpan<byte> indexSpan = new ReadOnlySpan<byte>(globalIndexData, (int)startIndexOffset, indexCount * indexStride);
            for (int i = 0; i < indexCount; i++)
            {
                int idx;
                if (indexStride == 4)
                {
                    idx = BinaryPrimitives.ReadInt32LittleEndian(indexSpan.Slice(i * 4));
                }
                else
                {
                    idx = BinaryPrimitives.ReadUInt16LittleEndian(indexSpan.Slice(i * 2));
                }

                indices[i] = idx;
                if (idx < minIndex) minIndex = idx;
                if (idx > maxIndex) maxIndex = idx;
            }

            // 2. VERTICES
            int vertexCount = (maxIndex - minIndex) + 1;
            if (vertexCount <= 0) return null;

            var rawPos = new Vector3[vertexCount];
            var posW = new Vector4[vertexCount];
            var normals = new Vector3[vertexCount];
            var uvChannels = new Dictionary<int, Vector2[]>();
            var colors = new Vector4[vertexCount];
            bool hasColors = false;

            var elementsToRead = new List<ElementInfo>();
            var slotOffsets = new Dictionary<int, int>();

            foreach (var element in layout.Elements)
            {
                int slot = element.InputSlot;
                if (!slotOffsets.ContainsKey(slot)) slotOffsets[slot] = 0;
                elementsToRead.Add(new ElementInfo { Desc = element, Offset = slotOffsets[slot] });
                slotOffsets[slot] += GetFormatSize((int)element.Format);
            }

            // PASS 1: Position
            foreach (var item in elementsToRead)
            {
                if (GetSemanticName(layout, item.Desc) != "POSITION") continue;

                ReadBuffer(bundle, mesh, vbMap, item.Desc, item.Offset, minIndex, vertexCount, (span, i) =>
                {
                    var (raw, decompressed, w) = ReadPositionFull(span, (int)item.Desc.Format, mesh);
                    rawPos[i] = raw;
                    posW[i] = new Vector4(decompressed, w);
                });
            }

            // PASS 2: Normals/UV
            foreach (var item in elementsToRead)
            {
                string semantic = GetSemanticName(layout, item.Desc);
                if (semantic == "POSITION") continue;

                if (semantic == "TEXCOORD" && !uvChannels.ContainsKey(item.Desc.SemanticIndex))
                    uvChannels[item.Desc.SemanticIndex] = new Vector2[vertexCount];

                ReadBuffer(bundle, mesh, vbMap, item.Desc, item.Offset, minIndex, vertexCount, (span, i) =>
                {
                    if (semantic == "NORMAL")
                        normals[i] = ReadNormal(span, (int)item.Desc.Format, posW[i].W);
                    else if (semantic == "TEXCOORD")
                        uvChannels[item.Desc.SemanticIndex][i] = ReadUV(span, (int)item.Desc.Format);
                    else if (semantic == "COLOR" && item.Desc.SemanticIndex == 0)
                    {
                        colors[i] = ReadColor(span, (int)item.Desc.Format);
                        hasColors = true;
                    }
                });
            }

            uvChannels.TryGetValue(0, out var channel0Uvs);

            // TRANSFORM — only compute bone matrix, skip per-vertex transform.
            // The renderer uses RawPositions + PositionScale/Translate + BoneTransform directly,
            // so pre-transforming into Positions is unnecessary work.
            bool hasBone = boneMatrices != null && mesh.RigidBoneIndex >= 0 && mesh.RigidBoneIndex < boneMatrices.Length;
            var transform = hasBone ? boneMatrices[mesh.RigidBoneIndex] : Matrix4x4.Identity;

            // Re-index
            var finalIndices = new int[indices.Length];
            for (int i = 0; i < indices.Length; i++) finalIndices[i] = indices[i] - minIndex;

            // Lookup bone name from skeleton
            string boneName = string.Empty;
            if (hasBone && bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault() is SkeletonBlob skel)
            {
                if (mesh.RigidBoneIndex >= 0 && mesh.RigidBoneIndex < skel.Bones.Count)
                {
                    boneName = skel.Bones[mesh.RigidBoneIndex].Name;
                }
            }

            return new ForzaGeometryData
            {
                Name = name,
                MaterialName = matName,
                Positions = null, // Not pre-computed; renderer uses RawPositions path
                Normals = normals,
                UVs = channel0Uvs ?? Array.Empty<Vector2>(),
                UvChannels = uvChannels,
                Colors = hasColors ? colors : null,
                Indices = finalIndices,
                SourceMesh = mesh,
                RawPositions = rawPos,
                MinVertexIndex = minIndex,
                BoneTransform = transform,
                BoneIndex = mesh.RigidBoneIndex,
                BoneName = boneName,
                OriginalBoneTransform = transform
            };
        }

        private void ReadBuffer(
            Bundle bundle,
            MeshBlob mesh,
            Dictionary<int, VertexBufferBlob> vbMap,
            D3D12_INPUT_LAYOUT_DESC element,
            int offsetInStride,
            int minIndex,
            int count,
            Action<ReadOnlySpan<byte>, int> readAction)
        {
            var usage = mesh.VertexBuffers.FirstOrDefault(v => v.InputSlot == element.InputSlot);
            if (usage == null) return;

            // 1. Resolve Buffer (ID vs Index)
            VertexBufferBlob vb = null;
            if (vbMap.TryGetValue(usage.Index, out var vbById))
            {
                vb = vbById;
            }
            else if (usage.Index >= 0 && usage.Index < bundle.Blobs.Count)
            {
                vb = bundle.Blobs[usage.Index] as VertexBufferBlob;
            }

            if (vb == null) return;

            // 2. Determine Data Source (Header.Data vs Raw Blob Data)
            byte[] data;
            int baseOffset = 0;

            if (vb.Header?.GetRawData() != null && vb.Header.GetRawData().Length > 0)
            {
                // In-Memory Created: Pure Vertex Data (No Header) — use raw contiguous buffer
                data = vb.Header.GetRawData();
                baseOffset = 0;
            }
            else
            {
                // Loaded from File: Raw Blob Data (Includes 16-byte Header)
                data = vb.GetContents();
                baseOffset = MODEL_BUFFER_HEADER_SIZE;
            }

            if (data == null || data.Length == 0) return;

            long stride = vb.Header?.Stride > 0 ? vb.Header.Stride : usage.Stride;
            if (stride == 0) stride = 28; // Fallback

            long usageOffset = usage.Offset;

            // To avoid span slicing overhead in loop, create one large span
            ReadOnlySpan<byte> bufferSpan = new ReadOnlySpan<byte>(data);
            int bufferLen = data.Length;

            for (int i = 0; i < count; i++)
            {
                long vertexId = minIndex + i + mesh.IndexedVertexOffset;
                long addr = baseOffset + usageOffset + (vertexId * stride) + offsetInStride;

                if (addr >= 0 && addr + 4 <= bufferLen)
                {
                    readAction(bufferSpan.Slice((int)addr), i);
                }
            }
        }

        // Damage Morph Helpers

        private static Vector3[] DecodeMorphDeltas(MorphBufferBlob morphBlob, Vector3[] baseRaw, MeshBlob mesh)
        {
            if (baseRaw == null || baseRaw.Length == 0) return null;

            byte[] data;
            int baseOffset;
            var rawData = morphBlob.Header?.GetRawData();
            if (rawData != null && rawData.Length > 0)
            {
                data = rawData;
                baseOffset = 0;
            }
            else
            {
                data = morphBlob.GetContents();
                baseOffset = MODEL_BUFFER_HEADER_SIZE;
            }

            if (data == null || data.Length == 0) return null;

            int stride = morphBlob.Header?.Stride > 0 ? morphBlob.Header.Stride : 8;
            int fmt = (int)(morphBlob.Header?.Format ?? 0);
            int vertexCount = baseRaw.Length;
            var result = new Vector3[vertexCount];
            ReadOnlySpan<byte> span = new ReadOnlySpan<byte>(data);

            for (int i = 0; i < vertexCount; i++)
            {
                long addr = baseOffset + (long)(mesh.IndexedVertexOffset + i) * stride;
                if (addr < 0 || addr + stride > data.Length)
                {
                    result[i] = baseRaw[i];
                    continue;
                }

                var s = span.Slice((int)addr);
                float dx, dy, dz;

                if (fmt == 10) // R16G16B16A16_FLOAT
                {
                    dx = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s));
                    dy = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s.Slice(2)));
                    dz = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s.Slice(4)));
                }
                else // fmt == 13 SNORM16 (default)
                {
                    dx = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s) / 32767f, -1f, 1f);
                    dy = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s.Slice(2)) / 32767f, -1f, 1f);
                    dz = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s.Slice(4)) / 32767f, -1f, 1f);
                }

                result[i] = new Vector3(baseRaw[i].X + dx, baseRaw[i].Y + dy, baseRaw[i].Z + dz);
            }

            return result;
        }

        private static float HalfToFloat(ushort half)
        {
            int exp = (half >> 10) & 0x1F;
            int mant = half & 0x3FF;
            int sign = half >> 15;
            float f;
            if (exp == 0)       f = mant * (1f / (1 << 24));
            else if (exp == 31) f = mant == 0 ? float.PositiveInfinity : float.NaN;
            else                f = (mant + 1024) * (1f / (1 << (25 - exp)));
            return sign == 0 ? f : -f;
        }

        // Helpers
        private string GetSemanticName(VertexLayoutBlob layout, D3D12_INPUT_LAYOUT_DESC element) => (element.SemanticNameIndex >= 0 && element.SemanticNameIndex < layout.SemanticNames.Count) ? layout.SemanticNames[element.SemanticNameIndex] : "UNKNOWN";
        private int GetFormatSize(int fmt) => fmt switch { 6 => 12, 10 => 8, 13 => 8, 16 => 8, 24 => 4, 28 => 4, 35 => 4, 37 => 4, _ => 4 };

        private static (Vector3 Raw, Vector3 Decompressed, float W) ReadPositionFull(ReadOnlySpan<byte> span, int format, MeshBlob mesh)
        {
            if (format == 13) // SNORM16
            {
                float rx = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span) / 32767f, -1f, 1f);
                float ry = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span.Slice(2)) / 32767f, -1f, 1f);
                float rz = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span.Slice(4)) / 32767f, -1f, 1f);
                float w = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span.Slice(6)) / 32767f, -1f, 1f);
                float x = rx, y = ry, z = rz;

                // Optimization: Local variable fetch
                var scale = mesh.PositionScale;
                if (scale.X != 0 || scale.Y != 0 || scale.Z != 0) 
                {
                     // Use local scale/translate to avoid property overhead in tight loop?

                     var trans = mesh.PositionTranslate;
                     x = x * scale.X + trans.X;
                     y = y * scale.Y + trans.Y;
                     z = z * scale.Z + trans.Z;
                }
                // Fallback handled by scale check above 
                if (scale.X == 0 && scale.Y == 0 && scale.Z == 0)
                {
                    // Scale 1, Translate 0
                    // Already set x=rx, etc.
                }

                return (new Vector3(rx, ry, rz), new Vector3(x, y, z), w);
            }
            if (format == 6) // FLOAT32
            {
                float x = BitConverter.ToSingle(span);
                float y = BitConverter.ToSingle(span.Slice(4));
                float z = BitConverter.ToSingle(span.Slice(8));

                // Span-based reading of float
                // Assuming BitConverter/BinaryPrimitives available.
                
                return (new Vector3(x, y, z), new Vector3(x, y, z), 1f);
            }
            return (Vector3.Zero, Vector3.Zero, 0);
        }

        private static Vector3 ReadNormal(ReadOnlySpan<byte> span, int format, float wFromPos)
        {
            if (format == 6)
            {
                // Format 6: FLOAT32 XYZ
                float nx = BitConverter.ToSingle(span);
                float ny = BitConverter.ToSingle(span.Slice(4));
                float nz = BitConverter.ToSingle(span.Slice(8));
                return Vector3.Normalize(new Vector3(nx, ny, nz));
            }
            if (format == 37) 
            {
                float nx = wFromPos; 
                float ny = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span) / 32767f, -1f, 1f); 
                float nz = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(span.Slice(2)) / 32767f, -1f, 1f); 
                return Vector3.Normalize(new Vector3(nx, ny, nz)); 
            }
            if (format == 10) 
            { 
                 // Half Float
                 float nx = (float)BitConverter.UInt16BitsToHalf(BinaryPrimitives.ReadUInt16LittleEndian(span)); 
                 float ny = (float)BitConverter.UInt16BitsToHalf(BinaryPrimitives.ReadUInt16LittleEndian(span.Slice(2))); 
                 float nz = (float)BitConverter.UInt16BitsToHalf(BinaryPrimitives.ReadUInt16LittleEndian(span.Slice(4))); 
                 // Skip last 2 bytes (padding/w)
                 return Vector3.Normalize(new Vector3(nx, ny, nz)); 
            }
            if (format == 24) 
            { 
                uint v = BinaryPrimitives.ReadUInt32LittleEndian(span);
                float nx = ((v >> 0) & 0x3FF) / 1023f * 2f - 1f; 
                float ny = ((v >> 10) & 0x3FF) / 1023f * 2f - 1f; 
                float nz = ((v >> 20) & 0x3FF) / 1023f * 2f - 1f; 
                return Vector3.Normalize(new Vector3(nx, ny, nz)); 
            }
            return Vector3.UnitY;
        }

        private static Vector2 ReadUV(ReadOnlySpan<byte> span, int format)
        {
            if (format == 35) 
            {
                return new Vector2(
                    BinaryPrimitives.ReadUInt16LittleEndian(span) / 65535f, 
                    1f - (BinaryPrimitives.ReadUInt16LittleEndian(span.Slice(2)) / 65535f)
                );
            }
            if (format == 16) 
            {
                return new Vector2(
                    BitConverter.ToSingle(span), 
                    1f - BitConverter.ToSingle(span.Slice(4))
                );
            }
            return Vector2.Zero;
        }

        // Reads a vertex color. Handles R8G8B8A8_UNORM (4 bytes) and R32G32B32A32_FLOAT (16 bytes).
        private static Vector4 ReadColor(ReadOnlySpan<byte> span, int format)
        {
            if (format == 2 && span.Length >= 16)
            {
                return new Vector4(
                    BitConverter.ToSingle(span),
                    BitConverter.ToSingle(span.Slice(4)),
                    BitConverter.ToSingle(span.Slice(8)),
                    BitConverter.ToSingle(span.Slice(12)));
            }
            if (span.Length >= 4)
                return new Vector4(span[0] / 255f, span[1] / 255f, span[2] / 255f, span[3] / 255f);
            return Vector4.One;
        }
    }
}
