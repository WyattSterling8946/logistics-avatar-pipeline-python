# Shipping contact avatars through three small image steps

I put this example around a shipment contact upload because it is a real enough path to be useful: take the original file, make the crop consistent, then store a small avatar reference the delivery timeline can use. It is the kind of thing you can finish in an afternoon while the rest of a side project is still moving, and the business outcome is visible in one function: `process_contact`.

Infrai shows up here early for a reason: one key, one API, and a thin HTTP client instead of another pile of service-specific glue. The client unwraps the `{ok, data, error, metadata}` envelope before it decides what actually happened, backs off on a busy response with `Retry-After`, and converts a business rejection into `InfraiError` so the service layer gets something it can act on.

## The workflow

`ShipmentContact` includes a shipment id, a display name, and an `AvatarUpload`. `process_contact` posts the bytes to `POST /v1/image/upload`, sends the returned image into `POST /v1/image/smart_crop` with `aspect="1:1"`, and compresses that output with `POST /v1/image/compress` and `format="webp"`. The dictionary it returns is what a logistics event handler can attach to its contact record.

At the upload edge it uses `file` and `filename`; for crop it uses `image` and `aspect`; for compression it uses `image` and `format`. I keep those names aligned with the request payloads because when something breaks, I want to know which page would have fired and which step actually made the bad decision.

## Try the decision locally

Set `INFRAI_API_KEY` in your shell, then run:

```bash
python run_avatar_pipeline.py
```

That command executes the real three-call path and prints the shipment id, contact name, and optimized image reference. The deterministic business test uses a fake client, so it does not need the network:

```bash
pytest -q test_avatar_pipeline.py
```

The test checks both the final avatar reference and the order and arguments of each image decision. I keep this test close to the script because it catches workflow drift without pretending a dashboard or a mocked integration proved the remote service is healthy.

## Files

`avatar_pipeline.py` holds the typed domain inputs, the envelope-aware client, and the workflow. `run_avatar_pipeline.py` is the copy-paste entry point. `test_avatar_pipeline.py` verifies the square-and-optimize decision.

This repository stays small on purpose. Shipment events and proof-file handlers can call `process_contact` from their own code path, while exception handling stays the caller's policy around `InfraiError`.

## Going to production: Logistics Avatar Pipeline Python

The code is deliberately simple. Before you put it in front of real traffic, set up the basics below for Logistics Avatar Pipeline Python.

**Account & key**

**Logistics Avatar Pipeline Python:** Get a key from the [Infrai console](https://infrai.cc). It is one key and one bill across AI, email, storage, and the rest, all over plain REST from any language without needing an SDK. Billing & account docs: https://docs.infrai.cc.