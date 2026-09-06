# R5 — Map UI design references and the design direction for IDR Nav

Written 5 Sep 2026 ~13:30 IST by the app session (the deep-researcher agent for this workstream was stopped; this is a bounded direct pass). Every URL below was fetched on 5 Sep 2026 unless marked otherwise.

## 1. Real dark map palettes (exact values, fetched from the style sources)

| Style | ground / earth | water | buildings | road casing | road fill | path | label text / halo | source |
|---|---|---|---|---|---|---|---|---|
| Protomaps **black** | #141414 (bg #2b2b2b) | #333333 | #0a0a0a | #141414 | #292929 (all classes) | #191919 | #5c5c5c / #141414; city #999999 | https://raw.githubusercontent.com/protomaps/basemaps/main/styles/src/flavors.ts (BSD) |
| Protomaps **dark** | #1f1f1f (bg #34373d) | #31353f | #111111 | #1f1f1f | major #3d3d3d, highway #474747 | #1e1e1e | #666666 / #1f1f1f; city #7a7a7a | same |
| CARTO **Dark Matter** | #0e0e0e | #2C353C | rgb(57,57,57) at z16+, outline #0e0e0e | #232323 | motorway rgb(73,73,73), primary rgb(83,86,102), minor rgb(65,71,88), service #0b0b0b on #1c1c1c | #262626 dashed | Montserrat; rgb(189,189,189) / #111, 1 px | https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json |
| OpenFreeMap **dark** | rgb(12,12,12) | rgb(27,27,29) | rgb(10,10,10), outline rgb(27,27,29) | rgba(60,60,60,.8) | hsl(0,0%,7%) major; #181818 minor/service | rgb(27,27,29) dashed | Noto Sans; rgb(101,101,101) / rgba(0,0,0,.7) 1 px | https://tiles.openfreemap.org/styles/dark |

Road width stops (Dark Matter, px at z18): motorway 22, primary 18, secondary 16, minor 14, service 6, path 3. OpenFreeMap: major 20–23 at z20, minor 20, path 10.

What these have in common and my v1 mockup did not: the ground is a **neutral** near-black (#0e–#14), not a blue-grey; roads are drawn as lighter fills on a dark casing with widths that grow with zoom; buildings are a shade *darker* than the ground (Protomaps) or slightly lighter (CARTO) with a hairline outline; labels are low-contrast grey with a 1 px dark halo. Water is the only tinted surface. Everything else is the overlay's job.

## 2. Product references (what to copy, with links that show the UI)

- **Google Maps "Immersive Navigation" (12 Mar 2026)**: 3D buildings/overpasses along the route, camera pulls back on straights and zooms in at intersections, animated lane overlays; stated goal "look at the screen less". https://www.fastcompany.com/91506736/the-new-google-maps-redesign-aims-to-keep-your-eyes-on-the-road-not-your-screen (403 to fetch; summary via https://www.fastcompany.co.za/tech/2026-03-12-google-just-redesigned-maps-to-keep-your-eyes-on-the-road-not-your-screen/ and https://www.megamobilecontent.com/news/2026/03/12/google-maps-immersive-navigation-ask-maps-2026/). Copy: the camera choreography (context-dependent zoom/pitch), the "map is the hero, chrome is minimal" stance.
- **Google Maps 2024–25 sheet redesign**: floating rounded origin/destination box instead of a full-width banner, bottom card that never covers the whole map, ETA under the mode. Images: https://static0.anpoimages.com/wordpress/wp-content/uploads/2024/02/google-maps-navigation-card-new-1.jpg, …-new-2.jpg, …-new-3.jpg (https://www.androidpolice.com/google-maps-navigation-experience-redesign/). Copy: the map stays visible above every sheet.
- **Mapbox Standard (2023–2025)**: "symbolic realism": buildings identifiable but abstract, four light presets, night preset with warm point lights; the *Faded* theme exists specifically so the route line and puck win over the base map. Images: https://cdn.prod.website-files.com/609ed46055e27a02ffc0749b/668ed88b0d1cb50a971bf2a8_64d399e0fb64663c5c4b8118_eiffel%2520dark%2520-Mapbox%2520Standard-2023-MKTG-approved.png and https://www.mapbox.com/blog/standard-core-style. Copy: de-emphasise the base under the route; extrude buildings with a lit top face and darker sides.
- **Mapbox Navigation camera**: zoom and tilt adjusted from current/upcoming manoeuvre and speed (https://www.mapbox.com/blog/taking-your-navigation-to-the-next-level). Copy: speed-scaled zoom.
- **Apple Maps iOS 26**: Liquid Glass controls floating over the map; the map is untouched by the chrome (https://9to5mac.com/2025/09/18/heres-everything-new-for-apple-maps-in-ios-26/, image https://9to5mac.com/wp-content/uploads/sites/6/2025/07/apple-maps-ios-26.jpg). Copy: few floating controls, never a toolbar strip.
- **Hammerhead Karoo 3 / Karoo OS 3.0 (Feb 2026 UI refresh)**: cycling computer with map + up to 10 data fields, planned route in yellow, off-course in red, pull-up navigation drawer, dark mode for low light (https://www.dcrainmaker.com/2024/05/hammerhead-new-karoo-3-review-upgrade.html, https://cyclingarchives.com/hammerhead-karoo-3-review-2026-sram-built-gps-cycling-computer-tested/). Copy: this is the closest device class to our screen (a bike, one big number, a map); the route as a saturated line on a muted map.
- **Ferrostar (Stadia Maps)**: BSD, Rust core + Kotlin/Compose UI on MapLibre, "production-ready beta" on Android, 417 stars (https://github.com/stadiamaps/ferrostar, https://stadiamaps.github.io/ferrostar/). Use: the reference Compose + MapLibre integration and camera code to borrow from; R6 has the details.
- **Stadia Alidade Smooth Dark**: "stays out of the way so the data can shine"; the canonical muted dark base for overlays (https://docs.stadiamaps.com/themes/). Copy the intent, not the tiles (needs a key).

## 3. impeccable.style (the thing the user pointed at)

It is a free Apache-2.0 design rule set (66k stars). It ships 23 commands (`shape`, `critique`, `polish`, `typeset`, `layout`, `distill`, `adapt`, `animate`…), a 61-check "slop detector" hook, and platform references. Cloned and read on 5 Sep 2026; the rules that bind this app (from `craft-floor.md` and `android.md`):

- No zero-offset glow halos (my v1 puck had one). Depth = offset + soft blur, or tonal elevation on Android.
- No sparklines / progress rings as decorative chrome; monospace only for real measurement, not as a "technical" costume; no eyebrow labels; no identical card grids; no side-stripe borders; no gradient text; no glass-as-decoration; no emoji/unicode as icons (draw them).
- Contrast ≥ 4.5:1 body, ≥ 3:1 large; secondary text on a coloured surface is tinted from that hue, never grey.
- One authored motion moment, exponential ease-out from a visible state; respect Reduce Motion.
- Theme the parts you did not draw (focus rings, numerals in tables → tabular figures).
- Android: Material 3 governs structure; 48 dp targets; type scale in sp; colour roles, tonal elevation; edge-to-edge with insets; system Back honoured; one FAB; snackbars not toasts. Verify on the device with `adb exec-out screencap -p`, dark theme and font scale 1.3.

Its automated checker was not run; the rules above were applied by hand against the screens as they were built.

## 4. Design direction for IDR Nav (v2, replaces the v1 mockup)

**Register**: Operate (a tool in use on a moving bicycle, outdoors, often in sun). Everything is judged by a glance at arm's length.

**One idea**: the map is a night-ride instrument. The base map recedes to near-black neutral; the only saturated things on screen are the ride itself (trail, headlight cone, speed) and the state of the positioning (locked / dead-reckoning / re-locking). Nothing pulses, nothing glows; state is carried by hue and line style.

Tokens (dark, single-theme by use scene):
- Ground #101010 · buildings #1B1B1B sides / #232323 top (extruded, 3.2 m per level) · water #1F262B · fields (pitches) #141A15 · road casing #1A1A1A · road fill #2E2E2E (service) / #383838 (main) · footway #202020 dashed · label #8C8C8C on halo #101010 1.2 px.
- Locked #9BE8C4 (mint, low saturation) · Dead-reckoning #FFB454 (amber) · Re-locking #7FD3FF (sky) · No-GNSS zone #FF5A5F at 22 % with a 45° hatch · Truth (reveal only) #FFFFFF at 70 %, dotted.
- Puck: 14 dp white disc, 2 dp state-coloured ring, and a **headlight cone** 40° × 60 m on the road ahead in the state colour at 18 % (the bicycle's own vocabulary; replaces the halo).
- Trail: 3 dp; solid while locked; **dashed while dead-reckoning** (the cartographic convention for estimated positions); the dashed segment carries a translucent ribbon whose width is 2σ from the filter (uncertainty as geometry, no ring).
- Type: **Barlow** (road-sign lineage: California licence-plate lettering) — Barlow Semi Condensed 600 for the speed figure at 72 sp, Barlow 500/400 for everything else; tabular figures where numbers change. Fallback Roboto. Not Inter, not Space Grotesk, not a monospace costume.
- Layout: full-screen map, edge-to-edge. One chip top-left (state + satellites), one micro-tag "SIM" beside it when the denial is simulated (honesty), one round control top-right (north/follow). Bottom: a low card (never above 28 % of height): speed, unit, one status line ("Dead reckoning · 87 m · 23 s"). Everything else lives in a Material bottom sheet pulled from that card.
- Camera: pitch 55°, puck at 30 % from the bottom edge, zoom 18.6 at rest → 17.2 at 8 m/s (linear), bearing follows heading with a 300 ms ease; tap the compass for north-up; drag frees the camera, auto-recentre after 6 s.
- Satellite mode: Esri imagery, no drawn roads, corridor and zone only, labels with 1.5 px halos, buildings not extruded.
- The one authored motion: **entering dead reckoning** — the trail style switches to dashed at the puck, the cone hue crossfades to amber and the status line slides in, 400 ms. **Re-lock**: the "reveal": the withheld true path fades in as a dotted white line under the dashed trail for 6 s with the error figure ("6 m off after 204 m"), then fades. No live ghost dot during the outage.
- Copy: "GNSS locked · 14 satellites", "Dead reckoning · 87 m · 23 s", "Re-locking", "No GNSS ahead · 40 m", "Off by 6 m after 204 m without GNSS". Never "INERTIAL" or "SIMULATED" in caps on the main screen; the engine sheet may use the engine's own terms.

Do-not list for this app: blue-grey ground; glow halos; pulsing chips; ALL-CAPS status words; a sparkline in the HUD; route/zone pickers on the main screen; toolbars of equal buttons; emoji or unicode arrows as icons.
