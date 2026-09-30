import io
import base64

from avatar_pipeline import AvatarUpload, InfraiClient, ShipmentContact, process_contact
from run_avatar_pipeline import sample_png


class FakeClient(InfraiClient):
    def __init__(self):
        super().__init__("test-key")
        self.calls = []

    def upload(self, image, filename):
        self.calls.append(("upload", filename, image.read()))
        return {"image": "uploaded-image"}

    def smart_crop(self, image, aspect="1:1"):
        self.calls.append(("smart_crop", image, aspect))
        return {"image": "square-image"}

    def compress(self, image, format="webp"):
        self.calls.append(("compress", image, format))
        return {"image": "optimized-avatar"}


def test_contact_avatar_is_square_and_optimized():
    client = FakeClient()
    result = process_contact(ShipmentContact("S1", "Ari", AvatarUpload("a.png", b"pixels")), client)
    assert result == {"shipment_id": "S1", "contact": "Ari", "avatar": "optimized-avatar"}
    assert client.calls == [
        ("upload", "a.png", b"pixels"),
        ("smart_crop", "uploaded-image", "1:1"),
        ("compress", "square-image", "webp"),
    ]


def test_upload_encodes_valid_image_as_base64():
    client = InfraiClient("test-key")
    calls = []
    client._json_request = lambda path, payload: calls.append((path, payload)) or {"image": "uploaded"}
    image = sample_png()
    assert client.upload(io.BytesIO(image), "mina.png") == {"image": "uploaded"}
    assert calls == [("/v1/image/upload", {"file": base64.b64encode(image).decode("ascii"), "filename": "mina.png"})]
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
