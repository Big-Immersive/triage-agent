# In-app feedback form

**For:** Mobile / web product teams

## The problem

The in-app form produces short, context-rich reports (the app version and device are attached automatically) but nobody processes them continuously.

## How the agents handle it

The form's backend POSTs each submission to the intake endpoint with `metadata: {app_version, device, os}`. With auto-run on, every submission is triaged within a minute of arrival. Metadata is used directly by `intake`, so even a one-line report is actionable.

## Example outcomes

- 'Love the new season but the shop crashes on my Xiaomi' + metadata → duplicate of the open shop-crash ticket → +1 comment noting the new device.
- A colour-blind mode request → feature_request → dropped from the bug flow (still visible under tickets › DROPPED).

## What to configure

- Intake endpoint
- auto-run on (default)

## Value

Zero-touch pipeline from form submission to ticket; product sees feature requests separated from bugs.
