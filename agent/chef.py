"""AI Cooking Teacher — technical test chef.

Joins the LiveKit call from the phone, hears the user, sees camera frames,
and talks back using Gemini Live (one model does hearing + seeing + voice).

Run it with:   uv run chef.py dev
"""

import json
import logging
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.agents.llm import ToolResult
from livekit.agents.utils import images
from livekit.agents.voice.agent_session import VoiceActivityVideoSampler
from livekit.plugins import google, silero
from livekit.plugins.google.realtime.realtime_api import DEFAULT_IMAGE_ENCODE_OPTIONS

from recipe import RECIPE, recipe_as_script

load_dotenv(".env.local")
logger = logging.getLogger("chef")

# ---------------------------------------------------------------------------
# Settings you might want to tweak during testing
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-3.8-live"
CHEF_VOICE = "Puck"  # one of Gemini's built-in voices
CHEF_NAME = "Chef"

# Camera frames sent to the AI. Every frame costs money AND stays in the
# AI's memory, so we only send them while the user is talking.
#   speaking: 1 photo per second while the user is talking
#   silent:   1 photo every 20 seconds as a safety net (set 0 for none)
FRAMES_PER_SEC_WHILE_SPEAKING = 1.0
FRAMES_PER_SEC_WHILE_SILENT = 0.05

# How long a pause (ms) Gemini waits for before deciding you've finished talking.
GEMINI_SILENCE_MS = 700

# Every photo sent to Gemini is also saved here so we can check what it saw.
DEBUG_FRAMES_DIR = Path(__file__).parent / "debug_frames"

AGENT_NAME = "chef"  # must match EXPO_PUBLIC_AGENT_NAME in the app's .env

STEPS = RECIPE["steps"]


def build_instructions() -> str:
    return f"""
You are {CHEF_NAME}, a warm, relaxed home-cooking mentor on a video call with a friend who
is learning to cook. Talk like a real person: natural, conversational, curious, a bit of
humor. React to what they say. Answer any question they have, cooking-related or not, and
chat freely when they want to. You are not reading from a script.

Tonight you're helping them make the recipe at the bottom. Treat it as your notes, not a
script: use your own words, adapt to how they're doing, skip or reorder things when it
makes sense, and offer swaps if they're missing something. Gently steer back to the cook
when it drifts, but never rush them.

LANGUAGE: always speak English, even if you think you heard another language.

THE CAMERA
- Their phone is propped up facing their counter. You get photos from it while they talk.
- Only describe what you can actually see in the latest photo. Never assume an object is a
  recipe ingredient just because it's in the recipe. If the image is unclear, too dark, or
  you can't tell what something is, say so plainly and ask them to bring it closer or turn
  the camera. Being honest beats being confident.
- If you haven't received a photo recently, say you can't see right now. Never describe
  something you haven't actually been shown.
- When they ask "does this look right?" or say they're done, look before you answer.

THE PHONE SCREEN (tools — use them quietly, don't announce them)
- go_to_step: call it whenever the cook moves on to a new recipe step (0 = gathering
  ingredients), so the step label on their screen stays right.
- start_timer / cancel_timer: start a timer whenever something needs timing; their phone
  counts down and you'll be told when it ends.

HOW TO TALK
- This is a spoken call: no lists, no markdown, no emoji. Usually a sentence or three,
  longer when they ask for an explanation.
- Long silences are normal; they're busy cooking. Don't fill them.
- Mention safety naturally when it matters (knife grip, hot oil, pan handles).
- When the dish is done, look at it, react honestly, and give a tip or two for next time.

YOUR NOTES ON TONIGHT'S RECIPE
{recipe_as_script()}
""".strip()


class FrameLogger:
    """Wraps the frame sampler: counts photos sent to Gemini and saves copies.

    Saved images are exactly what Gemini receives (same resize + JPEG settings).
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.total = 0
        self.this_turn = 0
        self.last_size = None
        DEBUG_FRAMES_DIR.mkdir(exist_ok=True)

    def __call__(self, frame: rtc.VideoFrame, session) -> bool:
        send = self.inner(frame, session)
        if not send:
            return False
        self.total += 1
        self.this_turn += 1
        size = (frame.width, frame.height)
        if size != self.last_size:
            logger.info("CAMERA: photo size sent to Gemini is now %dx%d", *size)
            self.last_size = size
        try:
            jpg = images.encode(frame, DEFAULT_IMAGE_ENCODE_OPTIONS)
            (DEBUG_FRAMES_DIR / "latest.jpg").write_bytes(jpg)
            (DEBUG_FRAMES_DIR / f"frame_{self.total % 30:02d}.jpg").write_bytes(jpg)
        except Exception:
            logger.exception("could not save debug frame")
        return True


class CookState:
    """What the phone screen shows. Mirrored to the phone as participant attributes."""

    def __init__(self) -> None:
        self.step_index = 0  # 0 = gather ingredients
        self.timers: dict[str, dict] = {}  # id -> {id, label, ends_at_ms}

    def to_json(self) -> str:
        if self.step_index == 0:
            title = "Gather ingredients"
        else:
            title = STEPS[self.step_index - 1]["title"]
        return json.dumps(
            {
                "recipe": RECIPE["title"],
                "step_index": self.step_index,
                "step_total": len(STEPS),
                "step_title": title,
                "timers": list(self.timers.values()),
            }
        )


def _quiet(text: str) -> ToolResult:
    """A tool result Gemini should NOT answer out loud.

    Screen updates (step label, timers) happen while the chef is already
    talking; asking for a reply made it repeat itself (e.g. greet 3 times).
    """
    return ToolResult(text, reply_required=False)


class Chef(Agent):
    def __init__(self, room: rtc.Room, state: CookState) -> None:
        super().__init__(instructions=build_instructions())
        self._room = room
        self._state = state

    async def publish_state(self) -> None:
        try:
            await self._room.local_participant.set_attributes({"cook_state": self._state.to_json()})
        except Exception:
            logger.exception("could not update phone screen state")

    @function_tool()
    async def go_to_step(self, context: RunContext, step_number: int) -> ToolResult:
        """Move the cook to a recipe step. Call this whenever you move on.

        Args:
            step_number: 0 for gathering ingredients, otherwise the recipe step number.
        """
        step_number = max(0, min(step_number, len(STEPS)))
        self._state.step_index = step_number
        await self.publish_state()
        logger.info("step -> %s", step_number)
        if step_number == 0:
            return _quiet("Screen updated: gather ingredients.")
        s = STEPS[step_number - 1]
        return _quiet(f"Screen updated: step {step_number}, {s['title']}.")

    @function_tool()
    async def start_timer(self, context: RunContext, label: str, minutes: float) -> ToolResult:
        """Start a countdown timer shown on the user's phone.

        Args:
            label: Short name, e.g. "Pasta" or "Onion".
            minutes: How long the timer runs, in minutes.
        """
        timer_id = uuid.uuid4().hex[:8]
        ends_at_ms = int((time.time() + minutes * 60) * 1000)
        self._state.timers[timer_id] = {"id": timer_id, "label": label, "ends_at_ms": ends_at_ms}
        await self.publish_state()
        logger.info("timer started: %s for %s min", label, minutes)
        return _quiet(f"Timer '{label}' started for {minutes} minutes.")

    @function_tool()
    async def cancel_timer(self, context: RunContext, label: str) -> ToolResult:
        """Cancel a running timer by its label.

        Args:
            label: The label of the timer to cancel.
        """
        removed = [k for k, t in self._state.timers.items() if t["label"].lower() == label.lower()]
        for k in removed:
            del self._state.timers[k]
        await self.publish_state()
        return _quiet(f"Cancelled {len(removed)} timer(s) named '{label}'.")


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    state = CookState()

    frames = FrameLogger(
        VoiceActivityVideoSampler(
            speaking_fps=FRAMES_PER_SEC_WHILE_SPEAKING,
            silent_fps=FRAMES_PER_SEC_WHILE_SILENT,
        )
    )

    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model=GEMINI_MODEL,
            voice=CHEF_VOICE,
            temperature=0.7,
            # google-genai's default API version 404s for Live models; v1beta works.
            api_version="v1beta",
            # Stops Gemini switching languages when it mishears a word.
            language="en-US",
            # Needed for "quiet" tool results (see _quiet) to stay quiet.
            tool_behavior=types.Behavior.NON_BLOCKING,
            # Without these, Gemini ends audio+video sessions after ~2 minutes.
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            session_resumption=types.SessionResumptionConfig(),
            # Gemini decides when you've started/finished talking. The phone sits
            # an arm's length away in a noisy kitchen, so make it quicker to
            # notice speech starting and quicker to decide you've finished.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=GEMINI_SILENCE_MS,
                ),
            ),
        ),
        # Local voice detection: only used to know when the user is speaking,
        # which controls when camera photos are sent and lets us measure delay.
        # (Gemini, not this, decides turns and interruptions.)
        vad=silero.VAD.load(),
        video_sampler=frames,
        # Cooking has long silences; never mark the user as "away".
        user_away_timeout=None,
    )

    chef = Chef(ctx.room, state)

    # ---- Diagnostics: what was heard, what was said ----------------------
    @session.on("user_input_transcribed")
    def _on_user_text(ev):
        if ev.is_final and ev.transcript.strip():
            logger.info("HEARD: %s", ev.transcript.strip())

    @session.on("conversation_item_added")
    def _on_item(ev):
        item = ev.item
        if getattr(item, "role", None) == "assistant":
            text = (item.text_content or "").strip()
            flag = " [CUT OFF]" if getattr(item, "interrupted", False) else ""
            logger.info("CHEF SAID%s: %s", flag, text[:300])

    @session.on("error")
    def _on_error(ev):
        logger.error("SESSION ERROR: %s", ev.error)

    # ---- Measurement: reply delay ("wake-up" delay) ---------------------
    timing = {"user_stopped": None, "last_agent_speech_end": time.time()}

    @session.on("user_state_changed")
    def _on_user_state(ev):
        if ev.new_state == "speaking":
            frames.this_turn = 0
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            timing["user_stopped"] = time.time()
            logger.info("you stopped talking; photos sent while you spoke: %d", frames.this_turn)

    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        now = time.time()
        if ev.new_state == "speaking" and timing["user_stopped"]:
            delay = now - timing["user_stopped"]
            silence = timing["user_stopped"] - timing["last_agent_speech_end"]
            logger.info(
                "REPLY DELAY %.2fs (after %.0fs since chef last spoke)%s",
                delay,
                silence,
                "  <-- over 1s target" if delay > 1.0 else "",
            )
            timing["user_stopped"] = None
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            timing["last_agent_speech_end"] = now

    # ---- Measurement: usage / cost --------------------------------------
    try:
        from livekit.agents import metrics

        usage = metrics.UsageCollector()

        @session.on("metrics_collected")
        def _on_metrics(ev):
            usage.collect(ev.metrics)

        async def _log_usage():
            logger.info("USAGE SUMMARY for this cook: %s", usage.get_summary())

        ctx.add_shutdown_callback(_log_usage)
    except Exception:
        logger.warning("usage metrics not available in this LiveKit version")

    # ---- Phone -> chef: a timer finished ---------------------------------
    # (registered below, after we've joined the room)
    async def _timer_done(data: rtc.RpcInvocationData) -> str:
        try:
            timer_id = json.loads(data.payload).get("id")
        except Exception:
            return "bad payload"
        timer = state.timers.pop(timer_id, None)
        if timer is None:
            return "unknown timer"
        await chef.publish_state()
        logger.info("timer finished: %s", timer["label"])
        session.generate_reply(
            instructions=(
                f"The '{timer['label']}' timer just finished. In one or two short sentences, "
                "tell the user what to do now for the current step."
            )
        )
        return "ok"

    await session.start(
        agent=chef,
        room=ctx.room,
        room_options=room_io.RoomOptions(video_input=True),
    )
    await ctx.connect()
    # The room's local participant only exists once we're connected.
    ctx.room.local_participant.register_rpc_method("timer_done", _timer_done)
    await chef.publish_state()
    await session.generate_reply(
        instructions="Greet the user warmly in one sentence, say what we're cooking, then start the kitchen check."
    )


if __name__ == "__main__":
    cli.run_app(server)
