/**
 * The call screen. Locked requirement: from start to wrap-up this looks like
 * one continuous FaceTime-style call. No screen switches, no spinners.
 *
 * Everything here is drawn by the phone (camera feed, step label, timers,
 * caption), so it stays "live" even while the AI is idle.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  useAnimatedValue,
  StyleSheet,
  Text,
  TouchableOpacity,
  Vibration,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useKeepAwake } from 'expo-keep-awake';
import { Ionicons } from '@expo/vector-icons';
import {
  AudioSession,
  useIOSAudioManagement,
  useLocalParticipant,
  useRoomContext,
  VideoTrack,
} from '@livekit/react-native';
import {
  TrackReference,
  useConnectionState,
  useSessionMessages,
} from '@livekit/components-react';
import {
  ConnectionState,
  LocalVideoTrack,
  Room,
  RoomEvent,
  Track,
  VideoPresets,
} from 'livekit-client';
import { useConnection } from '@/hooks/useConnection';

export default function CallScreen() {
  useKeepAwake(); // the phone sits propped up for 45 minutes; never let it sleep

  useEffect(() => {
    AudioSession.startAudioSession();
    return () => {
      AudioSession.stopAudioSession();
    };
  }, []);

  return <CallView />;
}

// ---------------------------------------------------------------------------
// State pushed by the chef (agent/chef.py -> CookState) via participant attributes
// ---------------------------------------------------------------------------
type Timer = { id: string; label: string; ends_at_ms: number };
type CookState = {
  recipe: string;
  step_index: number;
  step_total: number;
  step_title: string;
  timers: Timer[];
};

function useCookState(room: Room) {
  const [cookState, setCookState] = useState<CookState | null>(null);
  const [chefIdentity, setChefIdentity] = useState<string | null>(null);

  useEffect(() => {
    const read = () => {
      for (const p of room.remoteParticipants.values()) {
        const raw = p.attributes?.cook_state;
        if (raw) {
          try {
            setCookState(JSON.parse(raw));
            setChefIdentity(p.identity);
          } catch {
            // ignore malformed update
          }
          return;
        }
      }
    };
    read();
    room.on(RoomEvent.ParticipantAttributesChanged, read);
    room.on(RoomEvent.ParticipantConnected, read);
    return () => {
      room.off(RoomEvent.ParticipantAttributesChanged, read);
      room.off(RoomEvent.ParticipantConnected, read);
    };
  }, [room]);

  return { cookState, chefIdentity };
}

/** Ticks once per second. Timers live on the phone, so they work while the AI idles. */
function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function formatRemaining(ms: number) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------

const CallView = () => {
  const router = useRouter();
  const connection = useConnection();
  const room = useRoomContext();
  const connectionState = useConnectionState(room);
  useIOSAudioManagement(room, true);

  const { localParticipant, cameraTrack, isMicrophoneEnabled } =
    useLocalParticipant();
  const [facing, setFacing] = useState<'environment' | 'user'>('environment');

  // Turn on mic + back camera as soon as we're connected.
  useEffect(() => {
    if (connectionState !== ConnectionState.Connected) return;
    localParticipant.setMicrophoneEnabled(true).catch(console.warn);
    localParticipant
      // One 720p stream (no simulcast): the chef always gets a sharp enough
      // image to read labels, instead of LiveKit's small 360p layer.
      .setCameraEnabled(
        true,
        { facingMode: 'environment', resolution: VideoPresets.h720.resolution },
        { simulcast: false, videoEncoding: VideoPresets.h720.encoding }
      )
      .catch(console.warn);
  }, [connectionState, localParticipant]);

  const cameraRef: TrackReference | null = cameraTrack
    ? {
        participant: localParticipant,
        publication: cameraTrack,
        source: Track.Source.Camera,
      }
    : null;

  // ---- chef state, timers --------------------------------------------------
  const { cookState, chefIdentity } = useCookState(room);
  const now = useNow();
  const firedTimers = useRef(new Set<string>());

  useEffect(() => {
    if (!cookState || !chefIdentity) return;
    for (const t of cookState.timers) {
      if (t.ends_at_ms <= now && !firedTimers.current.has(t.id)) {
        firedTimers.current.add(t.id);
        Vibration.vibrate([0, 400, 200, 400]);
        localParticipant
          .performRpc({
            destinationIdentity: chefIdentity,
            method: 'timer_done',
            payload: JSON.stringify({ id: t.id }),
          })
          .catch((e) => console.warn('timer_done RPC failed', e));
      }
    }
  }, [now, cookState, chefIdentity, localParticipant]);

  // ---- caption: the chef's latest words, fading out after a few seconds ---
  const { messages } = useSessionMessages();
  const lastChefLine = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].from !== localParticipant) return messages[i].message;
    }
    return '';
  }, [messages, localParticipant]);

  const captionOpacity = useAnimatedValue(0);
  useEffect(() => {
    if (!lastChefLine) return;
    captionOpacity.setValue(1);
    const fade = Animated.timing(captionOpacity, {
      toValue: 0,
      duration: 800,
      delay: 7000,
      useNativeDriver: true,
    });
    fade.start();
    return () => fade.stop();
  }, [lastChefLine, captionOpacity]);

  // ---- controls (available, never required) --------------------------------
  const toggleMic = useCallback(() => {
    localParticipant
      .setMicrophoneEnabled(!isMicrophoneEnabled)
      .catch(console.warn);
  }, [localParticipant, isMicrophoneEnabled]);

  const flipCamera = useCallback(async () => {
    const next = facing === 'environment' ? 'user' : 'environment';
    const track = cameraTrack?.track as LocalVideoTrack | undefined;
    try {
      await track?.restartTrack({
        facingMode: next,
        resolution: VideoPresets.h720.resolution,
      });
      setFacing(next);
    } catch (e) {
      console.warn('camera flip failed', e);
    }
  }, [facing, cameraTrack]);

  const endCall = useCallback(() => {
    connection.disconnect();
    router.back();
  }, [connection, router]);

  const chefJoined = chefIdentity !== null;

  return (
    <View style={styles.root}>
      {/* Full-screen live camera feed */}
      {cameraRef ? (
        <VideoTrack
          trackRef={cameraRef}
          style={StyleSheet.absoluteFill}
          objectFit="cover"
          mirror={facing === 'user'}
        />
      ) : (
        <View style={[StyleSheet.absoluteFill, styles.noVideo]} />
      )}

      <SafeAreaView style={styles.overlay} pointerEvents="box-none">
        {/* Top: who we're talking to + current step + timers */}
        <View style={styles.top} pointerEvents="none">
          <Text style={styles.callerName}>Chef</Text>
          <Text style={styles.callerStatus}>
            {chefJoined ? (cookState?.recipe ?? '') : 'Calling…'}
          </Text>

          {cookState && (
            <View style={styles.stepPill}>
              <Text style={styles.stepText}>
                {cookState.step_index === 0
                  ? cookState.step_title
                  : `Step ${cookState.step_index}/${cookState.step_total} · ${cookState.step_title}`}
              </Text>
            </View>
          )}

          <View style={styles.timerRow}>
            {cookState?.timers.map((t) => {
              const remaining = t.ends_at_ms - now;
              const done = remaining <= 0;
              return (
                <View
                  key={t.id}
                  style={[styles.timerChip, done && styles.timerChipDone]}
                >
                  <Ionicons name="timer-outline" size={15} color="#fff" />
                  <Text style={styles.timerText}>
                    {t.label} {done ? 'done!' : formatRemaining(remaining)}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={styles.spacer} pointerEvents="none" />

        {/* Caption of what the chef just said */}
        <Animated.View
          style={[styles.caption, { opacity: captionOpacity }]}
          pointerEvents="none"
        >
          <Text style={styles.captionText} numberOfLines={3}>
            {lastChefLine}
          </Text>
        </Animated.View>

        {/* Controls */}
        <View style={styles.controls}>
          <RoundButton
            icon={isMicrophoneEnabled ? 'mic' : 'mic-off'}
            onPress={toggleMic}
            active={!isMicrophoneEnabled}
          />
          <RoundButton icon="camera-reverse" onPress={flipCamera} />
          <RoundButton icon="call" onPress={endCall} danger />
        </View>
      </SafeAreaView>
    </View>
  );
};

function RoundButton(props: {
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  danger?: boolean;
  active?: boolean;
}) {
  return (
    <TouchableOpacity
      onPress={props.onPress}
      activeOpacity={0.7}
      style={[
        styles.roundButton,
        props.active && styles.roundButtonActive,
        props.danger && styles.roundButtonDanger,
      ]}
    >
      <Ionicons
        name={props.icon}
        size={26}
        color={props.active ? '#000' : '#fff'}
        style={props.danger ? { transform: [{ rotate: '135deg' }] } : undefined}
      />
    </TouchableOpacity>
  );
}

const shadow = {
  textShadowColor: 'rgba(0,0,0,0.6)',
  textShadowOffset: { width: 0, height: 1 },
  textShadowRadius: 4,
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#000' },
  noVideo: { backgroundColor: '#111' },
  overlay: { flex: 1 },
  top: { alignItems: 'center', paddingTop: 8 },
  callerName: { color: '#fff', fontSize: 26, fontWeight: '600', ...shadow },
  callerStatus: { color: '#e5e5e5', fontSize: 15, marginTop: 2, ...shadow },
  stepPill: {
    marginTop: 12,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: 16,
    paddingVertical: 6,
    paddingHorizontal: 14,
  },
  stepText: { color: '#fff', fontSize: 15, fontWeight: '500' },
  timerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    marginTop: 8,
    gap: 8,
  },
  timerChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(255,149,0,0.85)',
    borderRadius: 14,
    paddingVertical: 5,
    paddingHorizontal: 11,
  },
  timerChipDone: { backgroundColor: 'rgba(255,59,48,0.95)' },
  timerText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  spacer: { flex: 1 },
  caption: {
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 14,
    padding: 12,
  },
  captionText: {
    color: '#fff',
    fontSize: 17,
    lineHeight: 23,
    textAlign: 'center',
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 28,
    paddingBottom: 12,
  },
  roundButton: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(255,255,255,0.22)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  roundButtonActive: { backgroundColor: '#fff' },
  roundButtonDanger: { backgroundColor: '#ff3b30' },
});
