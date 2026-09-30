# TinCan demo video

Hackathon demo, 1920×1080 at 60 fps.

- **v3** (current source, 42 s): [`tincan-demo-v3.mp4`](tincan-demo-v3.mp4). Redrawn people and a Prague street at dusk, and the Starship finale follows the real mission profile in four narrated steps: launch to orbit, orbital refueling, Trans-Mars injection, aerobrake-flip-land.
- **v2** (30 s): [`tincan-demo-v2.mp4`](tincan-demo-v2.mp4). First photoreal finale: Carol's building becomes one city light on Earth, strings spread city to city, a Starship carries the string to Mars. Source: commit `b107ff4`.
- **v1** (30 s): [`tincan-demo.mp4`](tincan-demo.mp4), with an all-vector finale. Source: commit `0a4c414`.

Built with [Remotion](https://www.remotion.dev). The Grok Bot desktop UI is recreated in React with colours sampled from the real app, so every click, message and camera move is scripted and frame-exact. Voiceover and music are generated with ElevenLabs.

## Storyboard

| Time | Scene | Voiceover |
| --- | --- | --- |
| 0–3 s | Marketplace: search "TinCan", click Add | "Your Grok Bot is brilliant. And alone." |
| 3–6 s | Create a group: Carol, Carol's Grok, Albina, Albina's Grok | "Add TinCan. Invite people and their bots." |
| 6–8 s | Tin-can GIF: the pairs connect | "Every pair, connected." |
| 8–17 s | Group chat: Carol asks Albina's Grok for the video, the bots trade screenshots, Albina says "Ship it" | "Ask anyone's bot. Bots hand work to each other. You just steer." |
| 17–20 s | Albina's Grok posts the video; the camera dives into it | "That's how we made this video. TinCan." |
| 19–23 s | Music only: zoom out from the bots to Carol and Albina, then to their street at dusk, each pair joined by a tin can | — |
| 23–25 s | The street shrinks into one light: Prague at dusk on the real Earth. Strings run from it to cities around the world | — |
| 25–28 s | Step 1: Super Heavy and Starship lift off from Starbase, hot-stage, the booster heads home, Starship reaches orbit | "To reach Mars, Starship rides Super Heavy to orbit." |
| 28–33 s | Step 2: a tanker docks tail to tail and fills the tanks while the next one waits | "Tankers dock, one after another, and top off its tanks." |
| 33–36.6 s | Step 3: the Trans-Mars injection burn; the string follows the ship across to Mars | "Then one long burn, straight for Mars." |
| 36.6–39.8 s | Step 4: belly-first aerobraking, flip, landing burn; a reply runs back to Earth | "Aerobrake. Flip. Land." |
| 39.8–42 s | End card: "Your people. Your bots. One conversation." | — |

## Re-render

```sh
cd demo-video
npm install
sh scripts/grok-sounds.sh   # copies the UI sounds from your local Grok Bot.app (not redistributed here)
npm run dev                 # Remotion Studio: scrub and preview
npm run render              # writes out/tincan-demo.mp4, loudness-normalised to -14 LUFS
```

The finale uses WebGL, so rendering runs Chrome with the ANGLE renderer (set in `remotion.config.ts`).

To regenerate the voiceover or music, put `ELEVENLABS_API_KEY=...` in `.env` and run `npm run audio` (or `npm run audio -- vo`, `npm run audio -- music`, `npm run audio -- v3` for the Starship lines and the finale music). `node scripts/stills.mjs 1.5 9 24` renders review stills at the given seconds.

## Files

- `src/app.tsx` – Grok Bot UI replica and the scripted marketplace, group and chat interactions
- `src/world.tsx` – the 2D zoom-out (bots → people → buildings) and the handoff to the 3D finale
- `src/space.tsx` – the 3D finale (three.js): Earth with day, night-lights and cloud layers, the city strings, a modelled Starship, Mars
- `public/space/` – NASA textures for the finale
- `src/scenes.tsx` – the tin-can beat and the end card
- `src/Demo.tsx` – timeline and audio mix
- `scripts/audio.mjs` – ElevenLabs voiceover (voice "Jessica") and music (Eleven Music v2.5)
- `scripts/finish.sh` – two-pass loudness normalisation

Credits: mouse click and whoosh from remotion.media; Grok Bot UI sounds (not included) from the Grok Bot app. Space imagery, all NASA and public domain: Blue Marble Next Generation (July 2004) and Blue Marble clouds (NASA Earth Observatory / Reto Stöckli), Black Marble 2016 city lights (NASA Earth Observatory), Mars from NASA 3D Resources, Milky Way from Deep Star Maps 2020 (NASA/Goddard Scientific Visualization Studio). The Starship is a simple model built in code, not SpaceX material.
