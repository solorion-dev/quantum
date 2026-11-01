# NebulaTV — Nebula for Google TV (NebulaTV-v0.1-experimental)

A leanback Android TV / Google TV client for **Nebula**. v1 is deliberately
thin: a full-screen WebView around the production Nebula web UI
(`https://nebula.solorion.dev`), packaged as a proper TV app.

Tracker: **TRK-0502**

## What v1 does

- **TV launcher presence** — `LEANBACK_LAUNCHER` intent, `android.software.leanback`
  required feature, touchscreen *not* required, 320×180 TV banner.
- **Remote-friendly** — D-pad focus navigation inside the page; **Back** walks
  the WebView history, then asks before exiting; **Menu** opens a small
  environment switcher (Production / Experimental), persisted across restarts.
- **Login that sticks** — cookies (including the DSECT session) are accepted,
  third-party cookies enabled, and flushed on pause, so sign-in survives
  app restarts.
- **Uploads** — the WebView file chooser is wired to the system document
  picker, so Nebula's MP4/audio upload fields can pick files the TV can see
  (e.g. USB storage, Downloads).
- **Offline/error handling** — a main-frame load failure shows a friendly
  retry page instead of a dead browser error.
- JavaScript, DOM storage, and media playback (no user-gesture requirement)
  enabled — generation previews and audio playback work as in the browser.

Default environment is **Production**. Press **Menu** on the remote to
switch to Experimental (`https://nebula-exp.solorion.dev`).

## Building

Canonical build (any normal machine, JDK 17 + Android SDK platform 36):

```
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

Fleet build note: the dev VM blocks JVM networking (Gradle daemon can't
run there), so the v0.1 APK was built on **Tritium**
(`/mnt/fast/android-sdk`, JDK 17) with this same wrapper.

## Installing (sideload)

```
adb connect <tv-ip>:5555        # or USB
adb install -r app-debug.apk
```

The app then appears in the TV launcher's app row as **Nebula**.

## Verification (v0.1, Nov 1, 2026)

Built on Tritium with the checked-in Gradle wrapper (AGP 8.5.2 / Kotlin
2.0.21, JDK 17, SDK platform 36): **BUILD SUCCESSFUL**, debug APK
856,585 bytes, SHA-256
`a8b1ac211ec3cf51ad928d58de90bfc891d6ffb5002f8d8edf04cb0e50d5d79e`.

- `aapt2 dump badging`: `leanback-launchable-activity` =
  `dev.solorion.nebulatv.MainActivity`; `uses-feature
  android.software.leanback` (required); touchscreen + microphone
  **not** required; application banner present.
- Installed and launched on an **Android TV emulator** (API 36,
  android-tv x86_64, AVD `nebula-tv-test` on Tritium). Screenshots in
  `screenshots/`:
  - `nebula-tv-apps-row.png` — the NEBULA banner card in the TV
    launcher's Installed Apps row.
  - `nebula-tv-inapp.png` — the app open on the live production Nebula
    (DSECT) login page, loaded over the network from the emulator.
  - `nebula-tv-menu-dialog.png` — the Menu-key environment switcher
    (Production selected by default).
- Not verified: an actual login (no credentials in the emulator), file
  upload through the picker, and behavior on physical Google TV
  hardware. Sideloading onto a real TV is Scotty's step.

## Known v1 gaps

- The Nebula web UI itself is not TV-optimized: D-pad navigation works, but
  dense desktop layouts need large-screen tolerance. A TV-tuned front end
  is a Nebula web project, not a shell change.
- File picking depends on what the TV's document picker can browse; no
  built-in media browser.
- No release signing yet — debug builds only. Play Store / Aptoide
  distribution is out of scope for v1.
- Long-press shortcuts, voice search, and recommendations rows are not
  implemented.

## Placement note

This app lives in the quantum monorepo under `apps/` per the Oct 15, 2026
monorepo rule (new Quantum apps start in the monorepo). Two tensions are
flagged for Scotty's review rather than silently resolved:

1. The Phase 2 monorepo restructure (`apps/` + `packages/`) has not landed
   yet, so `apps/nebula-tv/` is the first `apps/` resident and is a fully
   self-contained Gradle build — it is *not* wired into the root
   TypeScript workspace tooling.
2. `docs/MONOREPO.md`'s stack-affinity guardrail keeps foreign-runtime
   projects (e.g. `quantum-launcher`, Kotlin) in their own repos. This app
   was placed in the monorepo per the standing "new apps start in the
   monorepo" instruction; spinning it out later follows the normal
   spin-out path if Scotty prefers.
