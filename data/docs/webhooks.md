# Webhooks

## Overview
Webhooks let your application receive real-time notifications when events
happen in Nimbus, such as `payment.succeeded`, `subscription.cancelled`, or
`document.processed`. Configure endpoints under **Settings > Webhooks**.

## Verifying Signatures
Every webhook request includes an `X-Nimbus-Signature` header containing an
HMAC-SHA256 signature of the raw request body, signed with your endpoint's
signing secret (shown once at creation time, prefixed `whsec_`).

To verify:
1. Compute `HMAC-SHA256(signing_secret, raw_body)`.
2. Compare it to the value in `X-Nimbus-Signature` using a constant-time
   comparison.
3. Reject the request if they don't match, or if the `X-Nimbus-Timestamp`
   header is more than 5 minutes old (replay protection).

Always verify against the **raw** request body — re-serializing parsed JSON
will produce a different signature and cause valid webhooks to be rejected.

## Retry Behavior
If your endpoint doesn't return a `2xx` status within 10 seconds, Nimbus
retries delivery with exponential backoff: 1 min, 5 min, 30 min, 2 hours,
then once every 6 hours for up to 3 days. After 3 days of failed deliveries,
the event is marked `failed` and is visible in the dashboard's webhook log.

## Event Ordering
Nimbus does not guarantee that events are delivered in the order they
occurred — concurrent retries and queue rebalancing can reorder deliveries.
Each event includes a `created_at` timestamp; if your integration depends on
ordering, sort by this field rather than relying on delivery order.
