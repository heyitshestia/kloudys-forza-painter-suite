using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Text;
using Syroot.BinaryData;

namespace ForzaTools.CarScene
{
    public enum GameSeries
    {
        Auto = 0,
        Motorsport = 1,
        Horizon = 2
    }

    public class CarbinFile
    {
        public Scene Scene { get; set; }

        public void Load(Stream stream)
        {
            using var bs = new BinaryStream(stream);
            bs.ByteConverter = ByteConverter.Little;
            Scene = new Scene();
            Scene.Read(bs);
        }

        public void Save(Stream stream)
        {
            using var bs = new BinaryStream(stream);
            bs.ByteConverter = ByteConverter.Little;
            if (Scene != null)
                Scene.Serialize(bs);
        }

        public void ConvertToFH5()
        {
            if (Scene == null) return;
            Scene.ConvertToFH5();
        }
    }

    public class Scene
    {
        public ushort Version { get; set; }
        public GameSeries Series { get; set; } = GameSeries.Auto;
        public bool SeriesIsWeak { get; set; } = false;

        public Guid BuildGuid { get; set; }
        public bool BuildStrict { get; set; }
        public uint Ordinal { get; set; }
        public string MediaName { get; set; }
        public string SkeletonPath { get; set; }
        public LODFlags LODDetails { get; set; }
        public List<PartEntry> NonUpgradableParts { get; set; } = new();
        public List<UpgradablePart> UpgradableParts { get; set; } = new();
        public bool UnkV6 { get; set; } // Horizon v6+
        public bool UnkV7 { get; set; } // Horizon v7+

        public void Read(BinaryStream bs)
        {
            Version = bs.ReadUInt16();

            if (Series == GameSeries.Auto && Version == 7)
            {
                Series = GameSeries.Horizon;
            }
            else if (Series == GameSeries.Auto && (Version == 10 || Version == 11))
            {
                Series = GameSeries.Motorsport;
                SeriesIsWeak = true;
            }

            if (Version >= 3) BuildGuid = new Guid(bs.ReadBytes(16));
            if (Version >= 5) BuildStrict = bs.ReadBoolean();

            Ordinal = bs.ReadUInt32();
            MediaName = bs.ReadString(StringCoding.Int32CharCount);
            SkeletonPath = bs.ReadString(StringCoding.Int32CharCount);

            if (Version >= 2) LODDetails = new LODFlags(bs.ReadUInt16());

            uint nonUpgradableCount = bs.ReadUInt32();
            for (int i = 0; i < nonUpgradableCount; i++)
            {
                var entry = new PartEntry();
                entry.Read(bs, this);
                NonUpgradableParts.Add(entry);
            }

            uint upgradableCount = bs.ReadUInt32();
            for (int i = 0; i < upgradableCount; i++)
            {
                var part = new UpgradablePart();
                part.Read(bs, this);
                UpgradableParts.Add(part);
            }

            if (Series == GameSeries.Horizon && Version >= 6)
                UnkV6 = bs.ReadBoolean();

            if (Series == GameSeries.Horizon && Version >= 7)
                UnkV7 = bs.ReadBoolean();
        }

        public void Serialize(BinaryStream bs)
        {
            bs.WriteUInt16(Version);

            if (Version >= 3) bs.WriteBytes(BuildGuid.ToByteArray());
            if (Version >= 5) bs.WriteBoolean(BuildStrict);

            bs.WriteUInt32(Ordinal);
            bs.WriteString(MediaName, StringCoding.Int32CharCount);
            bs.WriteString(SkeletonPath, StringCoding.Int32CharCount);

            if (Version >= 2) bs.WriteUInt16(LODDetails.Value);

            bs.WriteUInt32((uint)NonUpgradableParts.Count);
            foreach (var entry in NonUpgradableParts)
                entry.Serialize(bs, this);

            bs.WriteUInt32((uint)UpgradableParts.Count);
            foreach (var part in UpgradableParts)
                part.Serialize(bs, this);

            if (Series == GameSeries.Horizon && Version >= 6)
                bs.WriteBoolean(UnkV6);

            if (Series == GameSeries.Horizon && Version >= 7)
                bs.WriteBoolean(UnkV7);
        }

        public void ConvertToFH5()
        {
            // set scene version
            Version = 6;
            Series = GameSeries.Horizon;
            SeriesIsWeak = false;
            UnkV6 = true; // Required by FH5
            UnkV7 = false;

            byte modelIdCounter = 0;

            foreach (var entry in NonUpgradableParts)
            {
                entry.Part.ConvertToFH5(ref modelIdCounter);
            }

            foreach (var part in UpgradableParts)
            {
                part.ConvertToFH5(ref modelIdCounter);
            }
        }
    }

    public class PartEntry
    {
        public CCarParts Type { get; set; }
        public Part Part { get; set; }

        public void Read(BinaryStream bs, Scene scene)
        {
            if (scene.Version >= 4)
            {
                if (scene.Series == GameSeries.Motorsport && scene.Version >= 6)
                {
                    Type = (CCarParts)bs.Read1Byte();
                }
                else
                {
                    Type = CCarPartsHelper.FromV1((CCarParts)bs.Read1Byte());
                }
                Part = new Part();
                Part.Read(bs, scene);
            }
            else
            {
                Part = new Part();
                Part.Read(bs, scene);
                Type = Part.Type;
            }
        }

        public void Serialize(BinaryStream bs, Scene scene)
        {
            if (scene.Version >= 4)
            {
                // Motorsport v6+ uses raw byte; older versions use the V1-mapped enum
            if (scene.Series == GameSeries.Motorsport && scene.Version >= 6)
                    bs.WriteByte((byte)Type);
                else
                    bs.WriteByte((byte)CCarPartsHelper.ToV1(Type));
                Part.Serialize(bs, scene);
            }
            else
            {
                Part.Serialize(bs, scene);
            }
        }
    }

    public class Part
    {
        public ushort Version { get; set; }
        public CCarParts Type { get; set; }
        public List<CarRenderModel> Models { get; set; } = new();
        public AABB Bounds { get; set; }

        public void Read(BinaryStream bs, Scene scene)
        {
            Version = bs.ReadUInt16();

            if (scene.Series == GameSeries.Motorsport && Version >= 3)
                Type = (CCarParts)bs.ReadUInt32();
            else
                Type = CCarPartsHelper.FromV1((CCarParts)bs.ReadUInt32());

            uint modelCount = bs.ReadUInt32();
            for (int i = 0; i < modelCount; i++)
            {
                var model = new CarRenderModel();
                model.Read(bs, scene);
                Models.Add(model);
            }

            if (Version >= 2) Bounds = AABB.Read(bs);
        }

        public void Serialize(BinaryStream bs, Scene scene)
        {
            bs.WriteUInt16(Version);

            if (scene.Series == GameSeries.Motorsport && Version >= 3)
                bs.WriteUInt32((uint)Type);
            else
                bs.WriteUInt32((uint)CCarPartsHelper.ToV1(Type));

            bs.WriteUInt32((uint)Models.Count);
            foreach (var model in Models)
                model.Serialize(bs, scene);

            if (Version >= 2) Bounds.Write(bs);
        }

        public void ConvertToFH5(ref byte idCounter)
        {
            Version = 2;
            foreach (var model in Models)
                model.ConvertToFH5(ref idCounter);

            // init bounds if missing
            if (Bounds.Min == Vector4.Zero && Bounds.Max == Vector4.Zero)
                Bounds = new AABB();
        }
    }

    public class UpgradablePart
    {
        public ushort Version { get; set; }
        public CCarParts Type { get; set; }
        public List<Upgrade> Upgrades { get; set; } = new();
        public List<SharedCarModel> SharedModels { get; set; } = new();

        public void Read(BinaryStream bs, Scene scene)
        {
            Version = bs.ReadUInt16();

            if (scene.Series == GameSeries.Motorsport && Version >= 4)
                Type = (CCarParts)bs.ReadUInt32();
            else
                Type = CCarPartsHelper.FromV1((CCarParts)bs.ReadUInt32());

            uint upgradeCount = bs.ReadUInt32();
            for (int i = 0; i < upgradeCount; i++)
            {
                var upg = new Upgrade();
                upg.Read(bs, scene, Version);
                Upgrades.Add(upg);
            }

            if (Version >= 3)
            {
                uint sharedCount = bs.ReadUInt32();
                for (int i = 0; i < sharedCount; i++)
                {
                    var shared = new SharedCarModel();
                    shared.Read(bs, scene);
                    SharedModels.Add(shared);
                }
            }
        }

        public void Serialize(BinaryStream bs, Scene scene)
        {
            bs.WriteUInt16(Version);

            if (scene.Series == GameSeries.Motorsport && Version >= 4)
                bs.WriteUInt32((uint)Type);
            else
                bs.WriteUInt32((uint)CCarPartsHelper.ToV1(Type));

            bs.WriteUInt32((uint)Upgrades.Count);
            foreach (var upg in Upgrades)
                upg.Serialize(bs, scene, Version);

            if (Version >= 3)
            {
                bs.WriteUInt32((uint)SharedModels.Count);
                foreach (var shared in SharedModels)
                    shared.Serialize(bs, scene);
            }
        }

        public void ConvertToFH5(ref byte idCounter)
        {
            Version = 3; // FH5 UpgradablePart Version

        // Migrate inline models from Upgrades to SharedModels (v3+)
        foreach (var upg in Upgrades)
            {
                if (upg.Models.Count > 0)
                {
                    foreach (var model in upg.Models)
                    {
                        SharedModels.Add(new SharedCarModel
                        {
                            UpgradeIds = new List<int> { upg.Id },
                            Model = model
                        });
                    }
                    upg.Models.Clear();
                }
            }

            foreach (var upg in Upgrades)
                upg.ConvertToFH5(ref idCounter);

            foreach (var shared in SharedModels)
                shared.Model.ConvertToFH5(ref idCounter);
        }
    }

    public class Upgrade
    {
        public ushort Version { get; set; }
        public byte Level { get; set; }
        public bool IsStock { get; set; }
        public int Id { get; set; }
        // m_ParentUpgradeId
        public int CarBodyId { get; set; }
        public bool ParentIsStock { get; set; }
        public List<CarRenderModel> Models { get; set; } = new();
        public AABB Bounds { get; set; }

        public void Read(BinaryStream bs, Scene scene, ushort parentPartVersion)
        {
            Version = bs.ReadUInt16();
            Level = bs.Read1Byte();
            IsStock = bs.ReadBoolean();
            Id = bs.ReadInt32();
            CarBodyId = bs.ReadInt32();
            ParentIsStock = bs.ReadBoolean();

            if (Version < 3)
            {
                uint modelCount = bs.ReadUInt32();
                for (int i = 0; i < modelCount; i++)
                {
                    var model = new CarRenderModel();
                    model.Read(bs, scene);
                    Models.Add(model);
                }
            }

            if (Version >= 2) Bounds = AABB.Read(bs);
        }

        public void Serialize(BinaryStream bs, Scene scene, ushort parentPartVersion)
        {
            bs.WriteUInt16(Version);
            bs.WriteByte(Level);
            bs.WriteBoolean(IsStock);
            bs.WriteInt32(Id);
            bs.WriteInt32(CarBodyId);
            bs.WriteBoolean(ParentIsStock);

            if (Version < 3)
            {
                bs.WriteUInt32((uint)Models.Count);
                foreach (var model in Models)
                    model.Serialize(bs, scene);
            }

            if (Version >= 2) Bounds.Write(bs);
        }

        public void ConvertToFH5(ref byte idCounter)
        {
            Version = 3;

            if (Bounds.Min == Vector4.Zero) Bounds = new AABB();
        }
    }

    public class SharedCarModel
    {
        public List<int> UpgradeIds { get; set; } = new();
        public CarRenderModel Model { get; set; }

        public void Read(BinaryStream bs, Scene scene)
        {
            uint count = bs.ReadUInt32();
            for (int i = 0; i < count; i++) UpgradeIds.Add(bs.ReadInt32());

            Model = new CarRenderModel();
            Model.Read(bs, scene);
        }

        public void Serialize(BinaryStream bs, Scene scene)
        {
            bs.WriteUInt32((uint)UpgradeIds.Count);
            foreach (int id in UpgradeIds) bs.WriteInt32(id);

            Model.Serialize(bs, scene);
        }
    }

    public class CarRenderModel
    {
        public ushort Version { get; set; }
        public string Path { get; set; }
        public Matrix4x4 Transform { get; set; }
        public LODFlags LODDetails { get; set; }
        public string BoneName { get; set; }
        public short BoneId { get; set; }
        public bool SnapToParent { get; set; }
        public DrawGroups DrawGroups { get; set; }
        public string AOSwatchPath { get; set; }

        public Dictionary<string, byte[]> MaterialOverrides { get; set; } = new();
        // m_PaintableGroups
        public List<MaterialIndexEntry> MaterialIndexes { get; set; } = new();

        public bool IsDroppable { get; set; }
        public float DropValue { get; set; }

        public int DropPartId { get; set; }

        public float BreakAmount { get; set; }
        public List<AOMapInfo> AOMapInfos { get; set; } = new();

        public bool IsInteriorWindshield { get; set; }
        public bool ReceivesImpact { get; set; }
        public bool ReceivesSplatter { get; set; }
        public uint ReceivesDamage { get; set; }
        public uint ReceivesDirt { get; set; }
        public uint ReceivesOil { get; set; }
        public uint ReceivesRubber { get; set; }
        public string AssemblyName { get; set; }
        public Guid GuidV13 { get; set; }
        public Guid DropGuidV14 { get; set; }
        public uint AOMapInfoIdV14 { get; set; }
        public List<Guid> DamageGuids { get; set; } = new();

        // Motorsport fields
        public uint ReceivesRain { get; set; }
        public byte ProxyLodId { get; set; }
        public string MotorsportUnkV18 { get; set; }
        public string MotorsportUnkV19 { get; set; }
        public bool IsInterior { get; set; }
        public uint IsLeftSideWindow { get; set; }
        public uint IsRightSideWindow { get; set; }
        public bool IsNascarWiper { get; set; }
        public bool IsLicensePlate { get; set; }

        // Horizon fields
        public int HorizonUnkV15 { get; set; }
        public byte HorizonId { get; set; }
        public uint HorizonUnkV18 { get; set; }
        public uint HorizonUnkV21Flag { get; set; }
        public string HorizonUnkV21Path { get; set; }

        // Preserved raw draw groups value for round-trip byte parity
        public int RawDrawGroupsValue { get; set; }

        public void Read(BinaryStream bs, Scene scene)
        {
            Version = bs.ReadUInt16();

            if (scene.Series == GameSeries.Auto || scene.SeriesIsWeak)
            {
                if (Version == 18 || Version == 15 || Version == 16 || (Version == 21 && scene.Version == 7))
                {
                    scene.Series = GameSeries.Horizon;
                }
                else
                {
                    scene.Series = GameSeries.Motorsport;
                }
                scene.SeriesIsWeak = false;
            }

            Path = bs.ReadString(StringCoding.Int32CharCount);
            Transform = ReadMatrix(bs);

            if (Version >= 5) LODDetails = new LODFlags(bs.ReadUInt16());
            else bs.ReadUInt32();

            BoneName = bs.ReadString(StringCoding.Int32CharCount);
            BoneId = bs.ReadInt16();
            SnapToParent = bs.ReadBoolean();

            // raw int32; preserved for round-trip accuracy
            RawDrawGroupsValue = bs.ReadInt32();
            DrawGroups = new DrawGroups(RawDrawGroupsValue);

            if (Version < 9) AOSwatchPath = bs.ReadString(StringCoding.Int32CharCount);

            if (Version >= 2)
            {
                uint overrideCount = bs.ReadUInt32();
                for (int i = 0; i < overrideCount; i++)
                {
                    string key = bs.ReadString(StringCoding.Int32CharCount);
                    uint len = bs.ReadUInt32();
                    byte[] data = bs.ReadBytes((int)len);
                    MaterialOverrides[key] = data;
                }
            }

            if (Version >= 3)
            {
                uint indexCount = bs.ReadUInt32();
                for (int i = 0; i < indexCount; i++)
                {
                    string key = bs.ReadString(StringCoding.Int32CharCount);
                    ulong val = 0;
                    if (Version >= 21)
                        val = bs.ReadUInt64();
                    else
                        val = unchecked((uint)bs.ReadInt32());
                    MaterialIndexes.Add(new MaterialIndexEntry { Key = key, Value = val });
                }
            }

            if (Version >= 6)
            {
                IsDroppable = bs.ReadBoolean();
                if (IsDroppable)
                {
                    DropValue = bs.ReadSingle();
                    DropPartId = bs.ReadInt32();
                }
            }

            if (Version >= 8) BreakAmount = bs.ReadSingle();

            if (Version >= 9)
            {
                uint aoCount = bs.ReadUInt32();
                for (int i = 0; i < aoCount; i++)
                {
                    var ao = new AOMapInfo();
                    ao.Read(bs);
                    AOMapInfos.Add(ao);
                }
            }

            if (Version >= 10) IsInteriorWindshield = bs.ReadBoolean();

            if (Version >= 11)
            {
                ReceivesImpact = bs.ReadBoolean();
                ReceivesSplatter = bs.ReadBoolean();
                ReceivesDamage = bs.ReadUInt32();
                ReceivesDirt = bs.ReadUInt32();
                ReceivesOil = bs.ReadUInt32();
                ReceivesRubber = bs.ReadUInt32();
            }

            if (Version >= 12) AssemblyName = bs.ReadString(StringCoding.Int32CharCount);

            if (Version >= 13) GuidV13 = new Guid(bs.ReadBytes(16));

            if (Version >= 14)
            {
                DropGuidV14 = new Guid(bs.ReadBytes(16));
                AOMapInfoIdV14 = bs.ReadUInt32();
            }

            if (scene.Series == GameSeries.Horizon && Version >= 15) HorizonUnkV15 = bs.ReadInt32();

            if ((scene.Series == GameSeries.Motorsport && Version >= 15) || (scene.Series == GameSeries.Horizon && Version >= 16))
            {
                uint dmgCount = bs.ReadUInt32();
                for (int i = 0; i < dmgCount; i++) DamageGuids.Add(new Guid(bs.ReadBytes(16)));
            }

            if (scene.Series == GameSeries.Motorsport)
            {
                if (Version >= 16) ReceivesRain = bs.ReadUInt32();
                if (Version >= 17) ProxyLodId = bs.Read1Byte();
                if (Version >= 18) MotorsportUnkV18 = bs.ReadString(StringCoding.Int32CharCount);
                if (Version >= 19) MotorsportUnkV19 = bs.ReadString(StringCoding.Int32CharCount);

                if (Version >= 20)
                {
                    IsInterior = bs.ReadBoolean();
                    IsLeftSideWindow = bs.ReadUInt32();
                    IsRightSideWindow = bs.ReadUInt32();
                    IsNascarWiper = bs.ReadBoolean();
                    IsLicensePlate = bs.ReadBoolean();
                }
            }
            else if (scene.Series == GameSeries.Horizon)
            {
                if (Version >= 17) HorizonId = bs.Read1Byte();
                if (Version >= 18) HorizonUnkV18 = bs.ReadUInt32();
                if (Version >= 21)
                {
                    HorizonUnkV21Flag = bs.ReadUInt32();
                    HorizonUnkV21Path = bs.ReadString(StringCoding.Int32CharCount);
                }
            }
        }

        public void Serialize(BinaryStream bs, Scene scene)
        {
            bs.WriteUInt16(Version);
            bs.WriteString(Path, StringCoding.Int32CharCount);
            WriteMatrix(bs, Transform);

            if (Version >= 5) bs.WriteUInt16(LODDetails.Value);
            else bs.WriteUInt32(0); // placeholder

            bs.WriteString(BoneName, StringCoding.Int32CharCount);
            bs.WriteInt16(BoneId);
            bs.WriteBoolean(SnapToParent);

            // RawDrawGroupsValue is synced by the conversion service
            bs.WriteInt32(DrawGroups.Value);

            if (Version < 9) bs.WriteString(AOSwatchPath ?? "", StringCoding.Int32CharCount);

            if (Version >= 2)
            {
                bs.WriteUInt32((uint)MaterialOverrides.Count);
                foreach (var kvp in MaterialOverrides)
                {
                    bs.WriteString(kvp.Key, StringCoding.Int32CharCount);
                    bs.WriteUInt32((uint)kvp.Value.Length);
                    bs.WriteBytes(kvp.Value);
                }
            }

            if (Version >= 3)
            {
                bs.WriteUInt32((uint)MaterialIndexes.Count);
                foreach (var item in MaterialIndexes)
                {
                    bs.WriteString(item.Key, StringCoding.Int32CharCount);
                    if (Version >= 21)
                        bs.WriteUInt64(item.Value);
                    else
                        bs.WriteInt32(unchecked((int)(uint)item.Value));
                }
            }

            if (Version >= 6)
            {
                bs.WriteBoolean(IsDroppable);
                if (IsDroppable)
                {
                    bs.WriteSingle(DropValue);
                    bs.WriteInt32(DropPartId);
                }
            }

            if (Version >= 8) bs.WriteSingle(BreakAmount);

            if (Version >= 9)
            {
                bs.WriteUInt32((uint)AOMapInfos.Count);
                foreach (var ao in AOMapInfos)
                    ao.Serialize(bs);
            }

            if (Version >= 10) bs.WriteBoolean(IsInteriorWindshield);

            if (Version >= 11)
            {
                bs.WriteBoolean(ReceivesImpact);
                bs.WriteBoolean(ReceivesSplatter);
                bs.WriteUInt32(ReceivesDamage);
                bs.WriteUInt32(ReceivesDirt);
                bs.WriteUInt32(ReceivesOil);
                bs.WriteUInt32(ReceivesRubber);
            }

            if (Version >= 12) bs.WriteString(AssemblyName ?? "", StringCoding.Int32CharCount);

            if (Version >= 13) bs.WriteBytes(GuidV13.ToByteArray());

            if (Version >= 14)
            {
                bs.WriteBytes(DropGuidV14.ToByteArray());
                bs.WriteUInt32(AOMapInfoIdV14);
            }

            if (scene.Series == GameSeries.Horizon && Version >= 15) bs.WriteInt32(HorizonUnkV15);

            if ((scene.Series == GameSeries.Motorsport && Version >= 15) || (scene.Series == GameSeries.Horizon && Version >= 16))
            {
                bs.WriteUInt32((uint)DamageGuids.Count);
                foreach (var guid in DamageGuids) bs.WriteBytes(guid.ToByteArray());
            }

            if (scene.Series == GameSeries.Motorsport)
            {
                if (Version >= 16) bs.WriteUInt32(ReceivesRain);
                if (Version >= 17) bs.WriteByte(ProxyLodId);
                if (Version >= 18) bs.WriteString(MotorsportUnkV18 ?? "", StringCoding.Int32CharCount);
                if (Version >= 19) bs.WriteString(MotorsportUnkV19 ?? "", StringCoding.Int32CharCount);
                if (Version >= 20)
                {
                    bs.WriteBoolean(IsInterior);
                    bs.WriteUInt32(IsLeftSideWindow);
                    bs.WriteUInt32(IsRightSideWindow);
                    bs.WriteBoolean(IsNascarWiper);
                    bs.WriteBoolean(IsLicensePlate);
                }
            }
            else if (scene.Series == GameSeries.Horizon)
            {
                if (Version >= 17) bs.WriteByte(HorizonId);
                if (Version >= 18) bs.WriteUInt32(HorizonUnkV18);
                if (Version >= 21)
                {
                    bs.WriteUInt32(HorizonUnkV21Flag);
                    bs.WriteString(HorizonUnkV21Path ?? string.Empty, StringCoding.Int32CharCount);
                }
            }
        }

        public void ConvertToFH5(ref byte idCounter)
        {
            Version = 18;

            HorizonId = idCounter++;

            // set Horizon-specific fields
            HorizonUnkV18 = 1;
            HorizonUnkV15 = 1;
            HorizonUnkV21Flag = 0;
            HorizonUnkV21Path = null;

            // clear Motorsport-only fields
            MotorsportUnkV18 = null;
            MotorsportUnkV19 = null;

            if (GuidV13 == Guid.Empty) GuidV13 = Guid.NewGuid();
            if (DropGuidV14 == Guid.Empty) DropGuidV14 = Guid.Empty;

            // required for v12+
            AssemblyName ??= "";

            // default LODDetails if unset
            if (LODDetails.Value == 0) LODDetails = new LODFlags(0x7E);

            // default v11 receiver fields if unset
            if (ReceivesDamage == 0) ReceivesDamage = 1;
            if (ReceivesDirt == 0) ReceivesDirt = 1;

            foreach (var ao in AOMapInfos)
                ao.ConvertToFH5();
        }

        private void WriteMatrix(BinaryStream bs, Matrix4x4 m)
        {
            bs.WriteSingle(m.M11); bs.WriteSingle(m.M12); bs.WriteSingle(m.M13); bs.WriteSingle(m.M14);
            bs.WriteSingle(m.M21); bs.WriteSingle(m.M22); bs.WriteSingle(m.M23); bs.WriteSingle(m.M24);
            bs.WriteSingle(m.M31); bs.WriteSingle(m.M32); bs.WriteSingle(m.M33); bs.WriteSingle(m.M34);
            bs.WriteSingle(m.M41); bs.WriteSingle(m.M42); bs.WriteSingle(m.M43); bs.WriteSingle(m.M44);
        }

        private Matrix4x4 ReadMatrix(BinaryStream bs)
        {
            float m11 = bs.ReadSingle(); float m12 = bs.ReadSingle(); float m13 = bs.ReadSingle(); float m14 = bs.ReadSingle();
            float m21 = bs.ReadSingle(); float m22 = bs.ReadSingle(); float m23 = bs.ReadSingle(); float m24 = bs.ReadSingle();
            float m31 = bs.ReadSingle(); float m32 = bs.ReadSingle(); float m33 = bs.ReadSingle(); float m34 = bs.ReadSingle();
            float m41 = bs.ReadSingle(); float m42 = bs.ReadSingle(); float m43 = bs.ReadSingle(); float m44 = bs.ReadSingle();
            return new Matrix4x4(
                m11, m12, m13, m14,
                m21, m22, m23, m24,
                m31, m32, m33, m34,
                m41, m42, m43, m44);
        }
    }

    public class AOMapInfo
    {
        public ushort Version { get; set; }
        public string Path { get; set; }
        public CCarParts PartType { get; set; }
        public int PartId { get; set; }
        public Guid DroppedModelInstanceGuid { get; set; }
        public bool IsDefault { get; set; }
        public sbyte LodTest { get; set; }
        public sbyte LodValue { get; set; }

        public void Read(BinaryStream bs)
        {
            Version = bs.ReadUInt16();
            Path = bs.ReadString(StringCoding.Int32CharCount);
            PartType = (CCarParts)bs.ReadUInt32();
            PartId = bs.ReadInt32();

            // v<2: skip unused int16+bool; v>=2: read GUID
            if (Version >= 2) DroppedModelInstanceGuid = new Guid(bs.ReadBytes(16));
            else { bs.ReadInt16(); bs.ReadBoolean(); }

            IsDefault = bs.ReadBoolean();

            if (Version >= 3)
            {
                LodTest = bs.ReadSByte();
                LodValue = bs.ReadSByte();
            }
        }

        public void Serialize(BinaryStream bs)
        {
            bs.WriteUInt16(Version);
            bs.WriteString(Path, StringCoding.Int32CharCount);
            bs.WriteUInt32((uint)PartType);
            bs.WriteInt32(PartId);

            if (Version >= 2) bs.WriteBytes(DroppedModelInstanceGuid.ToByteArray());
            else { bs.WriteInt16(0); bs.WriteBoolean(false); }

            bs.WriteBoolean(IsDefault);

            if (Version >= 3)
            {
                bs.WriteSByte(LodTest);
                bs.WriteSByte(LodValue);
            }
        }

        public void ConvertToFH5()
        {
            Version = 3;
            if (DroppedModelInstanceGuid == Guid.Empty)
                DroppedModelInstanceGuid = Guid.Empty;
        }
    }

    public class MaterialIndexEntry { public string Key; public ulong Value; }

    public struct LODFlags
    {
        public ushort Value;
        public LODFlags(ushort v) { Value = v; }
        public bool LODS => (Value & 1) != 0;
        public bool LOD0 => (Value & 2) != 0;
        public bool LOD1 => (Value & 4) != 0;
        public bool LOD2 => (Value & 8) != 0;
        public bool LOD3 => (Value & 16) != 0;
        public bool LOD4 => (Value & 32) != 0;
        public bool LOD5 => (Value & 64) != 0;
        public override string ToString() => $"0x{Value:X4}";
    }

    public struct DrawGroups
    {
        public int Value;
        public DrawGroups(int v) { Value = v; }
        public bool Exterior => (Value & 1) != 0;
        public bool Cockpit => (Value & 2) != 0;
        public bool Shadow => (Value & 4) != 0;
        public bool Hood => (Value & 8) != 0;
        public bool WindshieldReflection => (Value & 16) != 0;
        public bool DriverlessCockpit => (Value & 32) != 0;
        public bool WindshieldReflectionDriverlessCockpit => (Value & 64) != 0;
        public bool ProxyLOD => (Value & 128) != 0;
        public override string ToString() => $"0x{Value:X8}";
    }

    public struct AABB
    {
        public Vector4 Min;
        public Vector4 Max;
        public static AABB Read(BinaryStream bs)
        {
            return new AABB
            {
                Min = new Vector4(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle()),
                Max = new Vector4(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle())
            };
        }
        public void Write(BinaryStream bs)
        {
            bs.WriteSingle(Min.X); bs.WriteSingle(Min.Y); bs.WriteSingle(Min.Z); bs.WriteSingle(Min.W);
            bs.WriteSingle(Max.X); bs.WriteSingle(Max.Y); bs.WriteSingle(Max.Z); bs.WriteSingle(Max.W);
        }
        public override string ToString() => $"Min:{Min} Max:{Max}";
    }

    public enum CCarParts : uint
    {
        Engine = 0,
        Drivetrain = 1,
        CarBody = 2,
        Motor = 3,
        Brakes = 4,
        SpringDamper = 5,
        AntiSwayFront = 6,
        AntiSwayRear = 7,
        TireCompound = 8,
        RearWing = 9,
        RimSizeFront = 10,
        RimSizeRear = 11,
        Camshaft = 12,
        Valves = 13,
        Displacement = 14,
        PistonsCompression = 15,
        FuelSystem = 16,
        Ignition = 17,
        Exhaust = 18,
        Intake = 19,
        Flywheel = 20,
        Manifold = 21,
        RestrictorPlate = 22,
        OilCooling = 23,
        SingleTurbo = 24,
        TwinTurbo = 25,
        QuadTurbo = 26,
        SuperchargerCSC = 27,
        SuperchargerDSC = 28,
        Intercooler = 29,
        Clutch = 30,
        Transmission = 31,
        Driveline = 32,
        Differential = 33,
        FrontBumper = 34,
        RearBumper = 35,
        Hood = 36,
        SideSkirts = 37,
        TireWidthFront = 38,
        TireWidthRear = 39,
        WeightReduction = 40,
        ChassisStiffness = 41,
        Ballast = 42,        // FM2023+ only (v3 Part/UpgradablePart), absent in V1 mapping
        MotorParts = 43,
        WheelStyle = 44,
        Aspiration = 45,
    }

    public static class CCarPartsHelper
    {
        // Converts V1 part type (pre-Ballast) to current enum
        public static CCarParts FromV1(CCarParts val)
        {
            if ((uint)val >= 42) return (CCarParts)((uint)val + 1);
            return val;
        }

        // Converts current enum back to V1 format (pre-Ballast)
        public static CCarParts ToV1(CCarParts val)
        {
            if (val == CCarParts.Ballast) return (CCarParts)42; // best effort
            if ((uint)val > 42) return (CCarParts)((uint)val - 1);
            return val;
        }
    }
}