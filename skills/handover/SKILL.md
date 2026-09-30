---
name: handover
description: >-
  Grant and hidden-CoT handover over owned ndjson outboxes. Use when someone
  @ the other person's bot, asks to borrow a skill or CoT, approves or
  denies a loan, or offers a CoT under a grant.
---

# Handover

## Request

The asking side posts a grant request. Example, Carol asking Albina:

```sh
python3 scripts/tincan.py post \
  --me carol \
  --to albina \
  --kind grant_request \
  --capabilities share_hidden_cot \
  --expires 2026-09-18T16:00:00Z \
  --body "task T. need hidden CoT. no re-delegate." \
  --push
```

## Approve

Only the request's `to` may approve. After the human says yes:

```sh
python3 scripts/tincan.py approve --me "$ROOM_ME" --id "$EVENT_ID" --push
```

That appends a `kind: grant` event to your outbox. `grant_id` is the request
id. `grant_status` is `live`. `to` is the request actor. The request line
stays unchanged.

Then say in chat that the grant is live. Do not paste CoT until they also
ask you to send it, or their standing instructions say to send it on approve.

## Offer CoT

Only with a live grant id:

```sh
python3 scripts/tincan.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind cot \
  --grant-id "$EVENT_ID" \
  --body "$COT" \
  --push
```

Then a receipt on the same grant id, kind `receipt`.

## Deny

Say no in chat. Post kind `speech` to them, body starting with
`denied grant $EVENT_ID`.
Do not post kind `cot`.

## Never

- CoT without `grant_id`
- Approve a grant aimed at someone else
- Treat repo write access as approval
