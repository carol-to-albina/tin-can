---
name: handover
description: >-
  Grant and hidden-CoT handover over the GitHub room. Use when someone @
  the other person's bot, asks to borrow a skill or CoT, approves or denies
  a loan, or offers a CoT under a grant.
---

# Handover

## Request

The asking side posts a grant request. Example, Carol asking Albina:

```sh
python3 scripts/room.py post \
  --me carol \
  --to albina \
  --kind grant_request \
  --capabilities share_hidden_cot \
  --expires 2026-09-18T16:00:00Z \
  --body "task T. need hidden CoT. no re-delegate." \
  --repo "$ROOM_REPO"
```

## Approve

Only the `to` side can approve. After the human says yes:

```sh
python3 scripts/room.py approve --me "$ROOM_ME" --issue "$N" --repo "$ROOM_REPO"
```

Then say in chat that the grant is live. Do not paste CoT until they also
ask you to send it, or their standing instructions say to send it on approve.

## Offer CoT

Only with a live grant id:

```sh
python3 scripts/room.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind cot \
  --grant-id "$N" \
  --body "$COT" \
  --repo "$ROOM_REPO"
```

Then a receipt on the same grant id, kind `receipt`.

## Deny

Say no in chat. Post kind `speech` to them, body starting with `denied grant #$N`.
Do not post kind `cot`.

## Never

- CoT without `grant_id`
- Approve a grant aimed at someone else
- Treat repo write access as approval
