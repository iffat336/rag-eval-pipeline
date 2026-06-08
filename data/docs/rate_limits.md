# Rate Limits

## Limits by Key Type
| Key type     | Limit             | Burst   |
|--------------|-------------------|---------|
| Live (`nb_live_`) | 600 requests/minute | 50 req/sec |
| Test (`nb_test_`) | 60 requests/minute  | 10 req/sec |
| Service account   | 1200 requests/minute | 100 req/sec |

Limits are enforced per project, not per key — if a project has multiple live
keys, they share the same 600 requests/minute budget.

## Handling 429 Responses
When a request is rate limited, the API returns `429 rate_limited` with a
`Retry-After` header indicating how many seconds to wait before retrying.
Clients should implement exponential backoff with jitter:

```
wait = min(max_backoff, base * 2^attempt) + random(0, jitter)
```

Repeatedly retrying immediately after a 429 can extend the throttle window.

## Increasing Your Limit
Projects on the **Growth** and **Enterprise** plans can request a limit
increase from **Settings > Plan & Billing > Request Limit Increase**.
Increases typically take effect within one business day. Free and Starter
plans cannot request increases — upgrading the plan is required first.

## Webhook Delivery Limits
Webhook deliveries are not subject to the standard API rate limits, but
Nimbus will pause deliveries to an endpoint that returns five consecutive
non-2xx responses, and resume after 10 minutes with a single probe request.
