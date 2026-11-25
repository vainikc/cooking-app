# AI Cooking Teacher — Technical Test

A FaceTime-style call with an AI chef (Gemini Live), running one test recipe:
**Garlic Tomato Pasta**.

```
 iPhone app (app/)  ──live audio+video──▶  LiveKit Cloud  ◀──▶  Chef (agent/, runs on your Mac)  ◀──▶  Gemini Live
 camera, timers,                            (call relay)         recipe, steps, timers,
 step label, captions                                            delay + cost logging
```

- `app/` — the phone app (Expo / React Native)
- `agent/` — the chef. `chef.py` is the personality and rules, `recipe.py` is the recipe script

---

## One-time setup

### 1. Accept the Xcode license
Open the **Terminal** app and run this. It asks for your Mac password, and nothing shows as you type:
```
sudo xcodebuild -license accept
```

### 2. Get a Gemini API key
1. Go to https://aistudio.google.com and choose **Get API key** → **Create API key**.
2. Open `agent/.env.local` in any text editor. Paste the key after `GOOGLE_API_KEY=`.

### 3. Create a free LiveKit Cloud account
LiveKit relays the live audio and video between your phone and the chef.
1. Sign up at https://cloud.livekit.io and create a project. Any name works.
2. **Settings → API Keys**: create a key. Copy the three values into `agent/.env.local`:
   - `LIVEKIT_URL` (starts with `wss://`)
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
3. **Settings → Development token server**: turn it on and copy the **Token server ID**.
   Paste it into `app/.env` after `EXPO_PUBLIC_LIVEKIT_TOKEN_SERVER_ID=`.

> Never share or screenshot `agent/.env.local`. It holds secret keys.

### 4. Let Xcode install apps on your iPhone (free Apple ID is fine)
1. Open **Xcode → Settings → Accounts**, click **+**, and sign in with your Apple ID.
2. Plug your iPhone into the Mac with a cable. Tap **Trust** on the phone if asked.
3. On the iPhone: **Settings → Privacy & Security → Developer Mode → On**. The phone restarts.
   (This option only appears after the phone has been plugged into a Mac running Xcode.)

---

## Running a test cook

You need **two Terminal windows**. Keep both open the whole time.

**Window 1: start the chef**
```
cd ~/cooking-app/agent
uv run chef.py dev
```
Wait until you see `registered worker`. Leave this window open.

**Window 2: install and run the app on your phone** (iPhone plugged in, same Wi-Fi as the Mac)
```
cd ~/cooking-app/app
npx expo run:ios --device
```
- Pick your iPhone from the list.
- If it offers to install **CocoaPods**, say yes.
- The first build takes 5–15 minutes. Later builds are much faster.
- If it fails with a **signing** error, run `open ios/*.xcworkspace`. In Xcode, click the
  project at the top left, then **Signing & Capabilities**. Set **Team** to your name
  (Personal Team), then run the command again.
- If the phone says "Untrusted Developer": **Settings → General → VPN & Device Management**,
  tap your Apple ID, then **Trust**.

Then on the phone: tap **Start cooking**, allow camera and microphone, prop the phone up, and talk.

> With a free Apple ID, the app stops opening after 7 days. Run the command in window 2 again
> to reinstall. A paid Apple Developer account ($99/yr) removes that limit and enables TestFlight.

---

## What to watch during a test (the measurements from the spec)

Watch **window 1** (the chef):
- `REPLY DELAY 0.84s (after 312s since chef last spoke)`: how long until the chef starts
  answering after you stop talking. Target: **under ~1s**, especially after long silences.
  Anything over 1s is flagged `<-- over 1s target`.
- `USAGE SUMMARY for this cook: ...` is printed when the call ends. It shows the tokens used,
  which we convert into **cost per cook** using Gemini's pricing page.
- `step -> 3` and `timer started: ...` show the chef driving the phone screen.

Things to try:
- Say "done" and "does this look right?" with the board in view, and with it out of view.
- Say "hold on", stay silent for 5+ minutes, then say "I'm back". Check the reply delay.
- Let a timer run out. The phone should buzz and the chef should speak up.
- Run the range fan and water and leave a TV on. Does the chef still hear you? Does it answer the TV?

## Tweaking the chef
- Personality and rules: `build_instructions()` in `agent/chef.py`
- Voice and model: `CHEF_VOICE` and `GEMINI_MODEL` at the top of `agent/chef.py`
- Camera photos sent to the AI (cost): `FRAMES_PER_SEC_WHILE_SPEAKING` and `..._SILENT`
- Recipe: `agent/recipe.py`

After a change, stop window 1 with **Ctrl+C** and run `uv run chef.py dev` again.
Changes to the app's screens show up on the phone instantly while window 2 is running.

## Not in this test yet
Recipe library and upload, technique diagrams and step images, multiple chefs, wake words,
memory between cooks, and a real token server for launch.
