using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public sealed class ARTXMetadata : BundleMetadata
{
	public byte UnknownV1 { get; set; }
	public byte UnusedV2 { get; set; }
	public byte EnableAfterPixelDepth { get; set; }
	public byte FlagsV3 { get; set; }
	public byte UnknownV4 { get; set; }
	public byte UnknownV5 { get; set; }

	public bool HasFlagsV3 => Version >= 3 && EnableAfterPixelDepth != 0;
	public bool ForceAfterPixelDepth => (FlagsV3 & 0x08) != 0;
	public int ModeCodeV3 => DecodeModeCode(FlagsV3);

	public byte UnkV1 { get => UnknownV1; set => UnknownV1 = value; }
	public byte ReservedV2 { get => UnusedV2; set => UnusedV2 = value; }
	public byte HasFlagsBitmask { get => EnableAfterPixelDepth; set => EnableAfterPixelDepth = value; }
	public byte FlagsBitmask { get => FlagsV3; set => FlagsV3 = value; }
	public byte UnkV4 { get => UnknownV4; set => UnknownV4 = value; }
	public byte UnkV5 { get => UnknownV5; set => UnknownV5 = value; }
	public bool UsesBit3 => ForceAfterPixelDepth;

	public static int DecodeModeCode(byte flags)
	{
		bool hasBit1 = (flags & 0x02) != 0;
		bool hasBit2 = (flags & 0x04) != 0;

		if (hasBit1)
			return hasBit2 ? 33 : 35;

		return hasBit2 ? 34 : 0;
	}

	public override void ReadMetadataData(BinaryStream bs)
	{
		if (Version >= 1)
			UnknownV1 = bs.Read1Byte();

		if (Version >= 2)
		{
			UnusedV2 = bs.Read1Byte();
			EnableAfterPixelDepth = bs.Read1Byte();
		}

		if (HasFlagsV3)
			FlagsV3 = bs.Read1Byte();

		if (Version >= 4)
			UnknownV4 = bs.Read1Byte();

		if (Version >= 5)
			UnknownV5 = bs.Read1Byte();
	}

	public override void SerializeMetadataData(BinaryStream bs)
	{
		if (Version >= 1)
			bs.WriteByte(UnknownV1);

		if (Version >= 2)
		{
			bs.WriteByte(UnusedV2);
			bs.WriteByte(EnableAfterPixelDepth);
		}

		if (HasFlagsV3)
			bs.WriteByte(FlagsV3);

		if (Version >= 4)
			bs.WriteByte(UnknownV4);

		if (Version >= 5)
			bs.WriteByte(UnknownV5);
	}

	public override void CreateModelBinMetadataData(BinaryStream bs)
	{
		SerializeMetadataData(bs);
	}
}