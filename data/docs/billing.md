# Billing & Plans

## Plans
| Plan       | Monthly price | Included requests | Overage rate     |
|------------|---------------|-------------------|------------------|
| Free       | $0            | 10,000            | not available    |
| Starter    | $49           | 250,000           | $0.40 / 1,000    |
| Growth     | $249          | 2,000,000         | $0.25 / 1,000    |
| Enterprise | custom        | custom            | custom, negotiated |

Overage is billed monthly in arrears based on metered usage shown in
**Usage > Current Period**. Free plan projects are hard-capped — requests
beyond the included quota return `403 quota_exceeded` until the next period.

## Upgrading and Downgrading
Upgrades take effect immediately and are prorated for the remainder of the
billing cycle. Downgrades take effect at the start of the next billing cycle
to avoid losing access to usage you've already paid for.

## Invoices and Payment
Invoices are generated on the first day of each billing cycle and are due
within 14 days. Accepted payment methods are credit card and, for Growth and
Enterprise plans, ACH/wire transfer. Failed card payments are retried on
days 3, 7, and 14; after the third failure the project is moved to a
read-only state until payment succeeds.

## Cancelling
Cancelling a subscription stops future billing but does not delete project
data. Data is retained for 30 days after cancellation, after which it is
permanently deleted. Reactivating within the 30-day window restores the
project exactly as it was.
