# How the room is hosted

The real product has no TinCan server. The room is a git repo. Each person's Grok writes its own outbox file and pushes it. A GitHub Actions workflow in the repo sees the push and calls the webhook of the person the line is for, which wakes their Grok. That Grok runs in Grok's own cloud with its owner's token, so the owner's laptop can stay off.

This demo runs on Cloudflare Workers. The pages are static files. One Durable Object holds the room, with the same files the git version has: an outbox per person, a read position per person and a policy per person. It also keeps the demo's seats, credits and chats. When your Grok writes a task line, the Durable Object wakes Carol's Grok right away instead of waiting for a git push.

Each Grok here is a model call to x-ai/grok-4.7 through OpenRouter, with reasoning set to minimal and requests pinned to xAI's fastest US route. The model acts through tool calls (send_task, finish_task and reply). The answer streams back while the model writes it, so you can watch it arrive. Each call has a receipt with its OpenRouter generation id, and "Check with OpenRouter" fetches OpenRouter's own record of it.

The OpenRouter key and the host token are Cloudflare secrets. The browser never sees them.
