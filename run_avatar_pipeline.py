import struct
import zlib

from avatar_pipeline import ShipmentContact, AvatarUpload, client_from_environment, process_contact


def sample_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    width = height = 256
    row = b"\x00" + b"\x38\x8c\x99" * width
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def main() -> None:
    contact = ShipmentContact("SHP-2048", "Mina Chen", AvatarUpload("mina.png", sample_png()))
    result = process_contact(contact, client_from_environment())
    print(f"Processed avatar for {result['contact']} on {result['shipment_id']}: {result['avatar']}")


if __name__ == "__main__":
    main()
