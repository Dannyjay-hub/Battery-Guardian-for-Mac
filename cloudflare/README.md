# Battery Guardian Cloudflare Worker

This directory is the reproducible source for the deployed
`battery-guardian-download` Worker.

The `ANALYTICS` KV binding stores aggregate download counters and voluntary
Intel Battery Lab submissions. Telegram credentials must be configured as
Cloudflare secrets named `TG_BOT_TOKEN` and `TG_CHAT_ID`; they must never be
written into source files.

Before deployment, verify the download asset exists and test the Worker in a
preview. Deployments must preserve the existing KV namespace ID in
`wrangler.jsonc`.
