# TinCan demo video

30-second hackathon demo, 1920×1080 at 60 fps: [`tincan-demo.mp4`](tincan-demo.mp4).

Built with [Remotion](https://www.remotion.dev). The Grok Bot desktop UI is recreated in React with colours sampled from the real app, so every click, message and camera move is scripted and frame-exact. Voiceover and music are generated with ElevenLabs.

## Storyboard

| Time | Scene | Voiceover |
| --- | --- | --- |
| 0–3 s | Marketplace: search "TinCan", click Add | "Your Grok Bot is brilliant. And alone." |
| 3–6 s | Create a group: Carol, Carol's Grok, Albina, Albina's Grok | "Add TinCan. Invite people and their bots." |
| 6–8 s | Tin-can GIF: the pairs connect | "Every pair, connected." |
| 8–17 s | Group chat: Carol asks Albina's Grok for the video, the bots trade screenshots, Albina says "Ship it" | "Ask anyone's bot. Bots hand work to each other. You just steer." |
| 17–20 s | Albina's Grok posts the video; the camera dives into it | "That's how we made this video. TinCan." |
| 20–28 s | Music only: zoom out from the bots to people, buildings, continents, then Earth and Mars, each pair joined by a tin can | — |
| 28–30 s | End card: "Your people. Your bots. One conversation." | — |

## Re-render

```sh
cd demo-video
npm install
sh scripts/grok-sounds.sh   # copies the UI sounds from your local Grok Bot.app (not redistributed here)
npm run dev                 # Remotion Studio: scrub and preview
npm run render              # writes out/tincan-demo.mp4, loudness-normalised to -14 LUFS
```

To regenerate the voiceover or music, put `ELEVENLABS_API_KEY=...` in `.env` and run `npm run audio` (or `npm run audio -- vo`, `npm run audio -- music`). `node scripts/stills.mjs 1.5 9 24` renders review stills at the given seconds.

## Files

- `src/app.tsx` – Grok Bot UI replica and the scripted marketplace, group and chat interactions
- `src/world.tsx` – the zoom-out finale (bots → people → buildings → continents → Earth and Mars)
- `src/scenes.tsx` – the tin-can beat and the end card
- `src/Demo.tsx` – timeline and audio mix
- `scripts/audio.mjs` – ElevenLabs voiceover (voice "Jessica") and music (Eleven Music v2.5)
- `scripts/finish.sh` – two-pass loudness normalisation

Credits: mouse click and whoosh from remotion.media; globe outlines from world-atlas (Natural Earth); Grok Bot UI sounds (not included) from the Grok Bot app.
