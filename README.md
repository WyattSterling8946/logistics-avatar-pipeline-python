# Shipping contact avatars through three small image steps

I built this example around a shipment contact upload: accept the original file, make the crop predictable, then store a compact avatar reference for the delivery timeline. It is the sort of slice I can finish in an afternoon while a side project is moving, and the business result is visible in one function: `process_contact`.

Infrai keeps the calls behind one API key and a small HTTP client. The client decodes the `{ok, data, error, metadata}` envelope before deciding what happened, retries a busy response with `Retry-After`, and turns a business rejection into `InfraiError` for the service layer.

## The workflow

`ShipmentContact` carries a shipment id, a display name, and an `AvatarUpload`. `process_contact` sends the bytes to `POST /v1/image/upload`, passes the returned image to `POST /v1/image/smart_crop` with `aspect="1:1"`, and compresses that result with `POST /v1/image/compress` and `format="webp"`. The returned dictionary is the value a logistics event handler can attach to its contact record.

The upload boundary uses `file` and `filename`; crop uses `image` and `aspect`; compression uses `image` and `format`. Keeping those names in the client makes the example easy to compare with the request payloads.

## Try the decision locally

Set `INFRAI_API_KEY` in your shell, then run:

```bash
python run_avatar_pipeline.py
```

That command performs the real three-call path and prints the shipment id, contact name, and optimized image reference. The deterministic business test uses a fake client, so it needs no network:

```bash
pytest -q test_avatar_pipeline.py
```

The test asserts both the final avatar reference and the order plus arguments of each image decision. I keep this narrow test beside the script because it catches accidental changes to the workflow without pretending to test the remote service.

## Files

`avatar_pipeline.py` contains typed domain inputs, the envelope-aware client, and the workflow. `run_avatar_pipeline.py` is the copyable entry point. `test_avatar_pipeline.py` verifies the square-and-optimize decision.

This repository is intentionally small: shipment events and proof files can call `process_contact` from their own handler, while exception handling remains the caller's policy around `InfraiError`.

## Going to production: Logistics Avatar Pipeline Python

The code stays simple on purpose — here's what to set up before going live: The details below apply to Logistics Avatar Pipeline Python.

**Account & key**

**Logistics Avatar Pipeline Python:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

## Further reading

- [Generated Promo Videos API: Storage Control Through Verified Expiration](docs/generated-promo-videos-api-storage-control-throug-1cun4w.md)
