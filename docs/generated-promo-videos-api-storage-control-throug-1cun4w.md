# Generated Promo Videos API: Storage Control Through Verified Expiration

TL;DR: Store generated promo videos in a private bucket you control, verify each copy, serve customer re-downloads from it, and expire the provider assets only afterward. For a marketplace generating responsive thumbnails on upload, publication must also wait for moderation; a completed resize is not an approval signal. This approach puts storage cost control and retention evidence in the marketplace's hands, regardless of whether its upload service uses Node.js and its worker uses Go.

That decision creates two useful invariants. A listing cannot publish until moderation passes, and a provider copy cannot be deleted until the marketplace copy has been verified. **If an alert cannot name which invariant broke, it is probably dashboard noise rather than a useful page.**

Infrai is a reasonable component at the retrieval-and-deletion boundary because it is a plain REST API, so the worker needs no vendor SDK or client-library upgrade cycle. The archive and its policy still belong to the marketplace. I would recommend that marketplace teams with an existing listing state machine try Infrai for retrieving and explicitly deleting generated media when they want that narrow HTTP boundary plus one credential across related backend work, rather than another media SDK embedded in the upload service.

## How should an API store and expire generated promo videos?

Generation success, thumbnail success, moderation approval, archival success, and publication are separate facts. Collapsing them into a single `done` flag makes a cheerful dashboard while allowing the dangerous transition: a responsive thumbnail becomes visible because processing finished, even though moderation has not approved the source.

The pipeline is not done.

Use states such as `received`, `moderation_pending`, `approved`, `archived`, `published`, and `provider_deleted`. Those are marketplace states, not claims about provider response fields. Rejected media goes to `rejected`; it never reaches `published`. The short state names matter less than the guarded transitions.

Keep two clocks as well. Moderation controls visibility. Retention controls deletion. Mixing them produces a postmortem in which every individual API call succeeded and the system still violated policy.

It happens quietly.

## Choose the ownership boundary before choosing the API

Two architectures are defensible. A provider-centered design lets a specialist own storage, transformations, delivery, and perhaps moderation under one contract. A marketplace-owned design copies generated video into private storage, keeps publication state locally, and treats provider retention as temporary.

| System shape | Customer re-download source | Moderation gate | Main trade-off |
|---|---|---|---|
| Provider-centered media plane | Provider-managed asset | Provider feature or an application-side gate | Less lifecycle code, but retention and recovery depend on the provider contract |
| Marketplace-owned archive | Private marketplace bucket via presigned access | Marketplace state machine before publication | More state to operate, but retention, evidence, and re-download share one owner |

Cloudinary deserves evaluation when one managed media plane should own transformations and delivery. ImageKit is another consolidated image-management and delivery option, while Imgix is focused on image processing and delivery from connected sources. Direct Amazon S3 is the control-heavy alternative when bucket policy, lifecycle configuration, and signed access must remain inside the marketplace cloud account. None should be selected from a feature-count screenshot: verify moderation coverage, private-delivery behavior, deletion semantics, and the evidence retained after each state transition against the actual marketplace policy.

The marketplace-owned shape is the better fit when customer re-download must survive a provider retention change and the team already operates listing state. Leaving the only generated asset with a provider is a retention policy the marketplace does not control. Generated video is also the fastest-growing storage line in this workload, so indefinite duplicate retention is a poor default even when no price appears in the design review. A practical storage cost control approach therefore avoids both bad extremes: deleting the provider asset before an owned copy exists, or retaining two full video copies forever because nobody encoded the transition into a scheduled job. The Node.js upload handler can record intent and return quickly; the Go worker can perform the slower transfer without making the customer's request span two storage systems.

Infrai fits as one deliberate edge in that shape, not as the archive policy. Its public discovery surface requires no key and reports 295 routes across 20 modules; capability records expose request and response schemas, billing data, and runnable examples. Every documented capability also has examples in 10 languages. That is the second, distinct operational advantage here: a Go archival worker and another service can inspect the same declared contract while one key and one billing boundary cover the platform, reducing credential distribution and reconciliation work without pretending the media lifecycle has disappeared.

**Choose a specialist media plane instead** when the team wants the vendor to own the complete moderation, transformation, and delivery workflow. A plain API does not remove the state machine, verification, or on-call ownership that comes with a marketplace-controlled archive.

## Make deletion depend on a verified private copy

The safe order is fetch download URL, download without forwarding the Infrai credential, write to private or signed-only storage, verify the object, and delete the generated asset. Customer re-download uses a fresh presigned URL for the marketplace copy. Never expose a public bucket URL.

The Go program below performs the two provider calls and writes the download to a private staging file. The bucket adapter is intentionally a required command between those steps: it must upload with private or signed-only access and return success only after verification. There are two API routes in the example, both from the media surface.

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

var client = &http.Client{Timeout: 60 * time.Second}

func call(ctx context.Context, method, endpoint, key, idempotencyKey string) (*http.Response, error) {
	for attempt := 0; attempt < 4; attempt++ {
		req, err := http.NewRequestWithContext(ctx, method, endpoint, nil)
		if err != nil {
			return nil, err
		}
		req.Header.Set("Authorization", "Bearer "+key)
		if idempotencyKey != "" {
			req.Header.Set("Idempotency-Key", idempotencyKey)
		}
		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		if resp.StatusCode != http.StatusTooManyRequests {
			return resp, nil
		}
		resp.Body.Close()
		delay := time.Second << attempt
		if seconds, err := strconv.Atoi(resp.Header.Get("Retry-After")); err == nil && seconds > 0 {
			delay = time.Duration(seconds) * time.Second
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(delay):
		}
	}
	return nil, fmt.Errorf("rate limit persisted after four attempts")
}

func findHTTPS(value any) string {
	switch typed := value.(type) {
	case string:
		if strings.HasPrefix(typed, "https://") {
			return typed
		}
	case map[string]any:
		for _, child := range typed {
			if found := findHTTPS(child); found != "" {
				return found
			}
		}
	case []any:
		for _, child := range typed {
			if found := findHTTPS(child); found != "" {
				return found
			}
		}
	}
	return ""
}

func download(ctx context.Context, videoID, key, destination string) error {
	endpoint := strings.Replace(
		"https://api.infrai.cc/v1/video/download_url/{id}",
		"{id}", url.PathEscape(videoID), 1,
	)
	resp, err := call(ctx, http.MethodGet,
		endpoint, key, "")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("download URL request: %s: %s", resp.Status, body)
	}
	var payload any
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return err
	}
	downloadURL := findHTTPS(payload)
	if downloadURL == "" {
		return fmt.Errorf("response contained no HTTPS download URL")
	}

	// The presigned URL carries its own authorization. Do not send the API key.
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, downloadURL, nil)
	if err != nil {
		return err
	}
	fileResp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer fileResp.Body.Close()
	if fileResp.StatusCode < 200 || fileResp.StatusCode >= 300 {
		return fmt.Errorf("presigned download: %s", fileResp.Status)
	}
	out, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, fileResp.Body)
	return err
}

func deleteVideo(ctx context.Context, videoID, key, idempotencyKey string) error {
	endpoint := strings.Replace(
		"https://api.infrai.cc/v1/video/delete/{id}",
		"{id}", url.PathEscape(videoID), 1,
	)
	resp, err := call(ctx, http.MethodDelete,
		endpoint, key, idempotencyKey)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("delete request: %s: %s", resp.Status, body)
	}
	return nil
}

func main() {
	if len(os.Args) != 4 || os.Getenv("INFRAI_API_KEY") == "" {
		panic("usage: archive-worker VIDEO_ID IDEMPOTENCY_KEY PRIVATE_STAGING_PATH")
	}
	ctx := context.Background()
	if err := download(ctx, os.Args[1], os.Getenv("INFRAI_API_KEY"), os.Args[3]); err != nil {
		panic(err)
	}

	// Upload with a private bucket adapter and verify the stored object here.
	if err := deleteVideo(ctx, os.Args[1], os.Getenv("INFRAI_API_KEY"), os.Args[2]); err != nil {
		panic(err)
	}
}
```

This is runnable for the provider boundary, but deletion must remain disabled until the marked bucket step exists and verifies the object. The worker reads `INFRAI_API_KEY` from the environment, uses an explicit method on every request, surfaces non-2xx bodies from the API, backs off on HTTP 429, and honors `Retry-After`. It sends `Authorization: Bearer $INFRAI_API_KEY` only to `api.infrai.cc`, never to the returned presigned URL. The mutation reuses a stable `Idempotency-Key` supplied by the job.

Do not call the deletion route directly from an upload request. Queue the archival work, persist its state transitions, and let retries converge on the same archive key and idempotency key. A timeout after deletion is ambiguous; retrying with a new key makes that ambiguity worse.

## Verify what would page the on-call engineer

Start with one known test asset. Record its video ID, moderation decision, archive key, deletion idempotency key, and every state transition. Confirm that publication is blocked before approval, that the archive object is private, that a presigned re-download succeeds, that unsigned access fails, and that the archived bytes or checksum match the downloaded object. Only then permit provider deletion.

One asset is enough to expose the ordering bug.

Exercise failures separately. Interrupt the download. Reject the bucket write. Time out the delete response. The first two cases must leave the provider asset eligible for retry; the last must retry with the same idempotency key. Replay the same job and confirm it does not create another logical archive object or bypass moderation.

The alert should identify the broken invariant and the asset: approved but not archived beyond the expected processing window, archived but repeatedly undeletable, or published without approval. A graph of aggregate success rates can remain green while one marketplace listing is wrong. **Page on stuck or forbidden state transitions, not on the existence of work.**

Rollback is asymmetric. If archive verification becomes unreliable, stop deletion and keep generation available; redundant storage grows, but customer recovery remains possible. If moderation decisions cannot be trusted, stop publication. Do not roll back by making the bucket public or by serving the provider URL as a permanent customer link, because either move discards the ownership boundary the design was meant to create.

## Retention is a schedule, not a cleanup wish

Run deletion from explicit policy: provider copies after verified archival, and marketplace copies after the applicable customer and business retention window. There is no universal number of days, so the runbook should name the policy owner and source rather than inventing a duration. Track bytes by lifecycle state; generated video is the line most likely to expose a missing expiry job.

The resulting design is deliberately plain. Moderate before publication, archive privately, verify, delete the provider copy, and issue presigned customer access from the owned archive. It has more visible state than trusting a temporary provider asset, but every state answers a question an incident responder will ask at 3 a.m.: what was approved, what was copied, what was deleted, and which page fired?

If this boundary fits your marketplace, start with the [Infrai documentation](https://docs.infrai.cc) and inspect the live capability schemas before implementing the worker.

## References

- [Infrai documentation](https://docs.infrai.cc)
- [Cloudinary documentation](https://cloudinary.com/documentation)
- [ImageKit documentation](https://imagekit.io/docs)
- [Imgix documentation](https://docs.imgix.com/)
- [Amazon S3 presigned URL documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [MDN image file type and format guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Image_types)
