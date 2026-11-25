import { useConnection } from '@/hooks/useConnection';
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, View, Text, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

// Technical test: a single hard-coded recipe. The library comes later.
export default function StartScreen() {
  const router = useRouter();
  const { isConfigured, isConnectionActive, connect } = useConnection();

  useEffect(() => {
    if (isConnectionActive) {
      router.navigate('../assistant');
    }
  }, [isConnectionActive, router]);

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.kicker}>{"TONIGHT'S COOK"}</Text>
      <View style={styles.card}>
        <Text style={styles.title}>Garlic Tomato Pasta</Text>
        <Text style={styles.meta}>Serves 2 · about 30 min · Beginner</Text>
        <Text style={styles.body}>
          Prop your phone up so the camera sees your cutting board and stove.
          Then just talk to the chef. You won&apos;t need to touch the phone.
        </Text>
      </View>

      {!isConfigured && (
        <Text style={styles.warning}>
          Setup needed: add your LiveKit token server ID to app/.env (see
          README), then restart.
        </Text>
      )}

      <TouchableOpacity
        onPress={connect}
        style={[styles.button, !isConfigured && styles.buttonDisabled]}
        activeOpacity={0.8}
        disabled={!isConfigured || isConnectionActive}
      >
        <Text style={styles.buttonText}>Start cooking</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b0b0b',
    padding: 24,
    justifyContent: 'center',
  },
  kicker: {
    color: '#8a8a8a',
    fontSize: 13,
    letterSpacing: 1.5,
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#171717',
    borderRadius: 20,
    padding: 20,
    marginBottom: 32,
  },
  title: { color: '#fff', fontSize: 28, fontWeight: '700', marginBottom: 6 },
  meta: { color: '#a0a0a0', fontSize: 15, marginBottom: 16 },
  body: { color: '#d0d0d0', fontSize: 16, lineHeight: 23 },
  warning: {
    color: '#ffb340',
    fontSize: 14,
    marginBottom: 16,
    textAlign: 'center',
  },
  button: {
    backgroundColor: '#34c759',
    paddingVertical: 16,
    borderRadius: 30,
    alignItems: 'center',
  },
  buttonDisabled: { opacity: 0.4 },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '600' },
});
