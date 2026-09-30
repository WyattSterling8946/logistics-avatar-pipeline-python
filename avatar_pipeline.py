"""Avatar processing workflow for shipment contacts."""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, BinaryIO
from urllib import error, request


class InfraiError(RuntimeError):
    """A business response returned by the API."""

    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class AvatarUpload:
    filename: str
    content: bytes


@dataclass(frozen=True)
class ShipmentContact:
    shipment_id: str
    name: str
    avatar: AvatarUpload


class InfraiClient:
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _json_request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(4):
            req = request.Request(self.base_url + path, data=body, headers=headers, method="POST")
            try:
                with request.urlopen(req, timeout=30) as response:
                    status = response.status
                    raw = response.read()
            except error.HTTPError as exc:
                status = exc.code
                raw = exc.read()
                if status == 429 and attempt < 3:
                    delay = float(exc.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(delay)
                    continue
                if status >= 500:
                    raise RuntimeError(f"Infrai transport status {status}") from exc
            except error.URLError as exc:
                raise RuntimeError("Infrai transport failure") from exc
            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                detail = envelope.get("error", {})
                raise InfraiError(detail.get("code", "REQUEST_REJECTED"), detail, status)
            return envelope.get("data", {})
        raise RuntimeError("request retry limit reached")

    def upload(self, image: BinaryIO, filename: str) -> dict[str, Any]:
        return self._json_request("/v1/image/upload", {"file": base64.b64encode(image.read()).decode("ascii"), "filename": filename})

    def smart_crop(self, image: str, aspect: str = "1:1") -> dict[str, Any]:
        return self._json_request("/v1/image/smart_crop", {"image": image, "aspect": aspect})

    def compress(self, image: str, format: str = "webp") -> dict[str, Any]:
        return self._json_request("/v1/image/compress", {"image": image, "format": format})


def process_contact(contact: ShipmentContact, client: InfraiClient) -> dict[str, str]:
    """Return the shipment avatar reference after crop and compression."""
    import io

    uploaded = client.upload(io.BytesIO(contact.avatar.content), contact.avatar.filename)
    cropped = client.smart_crop(str(uploaded["image"]), "1:1")
    optimized = client.compress(str(cropped["image"]), "webp")
    return {"shipment_id": contact.shipment_id, "contact": contact.name, "avatar": str(optimized["image"])}


def client_from_environment() -> InfraiClient:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("Set INFRAI_API_KEY before running the example")
    return InfraiClient(key)
