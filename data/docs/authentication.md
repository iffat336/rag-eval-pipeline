# Authentication

## API Keys
Nimbus API requests are authenticated with an API key passed in the
`Authorization: Bearer <key>` header. Keys are created from the dashboard
under **Settings > API Keys** and are scoped to a single project.

Each key has a prefix that identifies its environment:
- `nb_live_...` — production keys, rate limited to 600 requests/minute
- `nb_test_...` — sandbox keys, rate limited to 60 requests/minute

Keys do not expire automatically, but can be revoked instantly from the
dashboard. Revoked keys return `401 Unauthorized` with the error code
`key_revoked`.

## OAuth 2.0
For applications acting on behalf of a user, Nimbus supports the OAuth 2.0
authorization code flow. Register a redirect URI in **Settings > OAuth Apps**,
then direct users to `https://auth.nimbus.dev/oauth/authorize`.

Access tokens issued via OAuth expire after 1 hour. Use the `refresh_token`
returned alongside the access token to obtain a new one from
`https://auth.nimbus.dev/oauth/token` without re-prompting the user.

## Service Accounts
Service accounts are non-human identities used for server-to-server
integrations such as CI pipelines or scheduled jobs. They authenticate using
a signed JWT (RS256) exchanged for a short-lived access token (15 minutes).
Service accounts cannot use the OAuth authorization code flow.

## Common Errors
- `401 invalid_api_key` — the key is malformed or doesn't exist
- `401 key_revoked` — the key was revoked from the dashboard
- `403 insufficient_scope` — the key's project does not have access to the
  requested resource
- `429 rate_limited` — too many requests; see the Rate Limits document for
  retry guidance
