// Setup code for LiveKit React-Native
import { registerGlobals } from '@livekit/react-native';
import { config as rxjsConfig } from 'rxjs';

registerGlobals();

// Hanging up while the chef is mid-sentence cuts off its live caption stream.
// LiveKit's caption reader (components-core) doesn't handle that error, so RxJS
// re-throws it as an uncaught error. It's expected on hang-up: ignore it.
// Anything else still surfaces normally.
rxjsConfig.onUnhandledError = (err: unknown) => {
  const e = err as { name?: string; message?: string } | undefined;
  if (
    e?.name === 'DataStreamError' ||
    /disconnected in the middle of receiving data/i.test(e?.message ?? '')
  ) {
    return;
  }
  setTimeout(() => {
    throw err;
  });
};
