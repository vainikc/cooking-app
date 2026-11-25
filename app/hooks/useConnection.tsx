import { TokenSource } from 'livekit-client';
import { createContext, useContext, useMemo, useState } from 'react';
import { SessionProvider, useSession } from '@livekit/components-react';

// Both values come from the app's ".env" file (see README).
// The token server lets the phone join a LiveKit call without holding any
// secret keys. It is LiveKit Cloud's built-in *development* token server:
// fine for testing on our own phones, must be replaced before launch.
const tokenServerId = process.env.EXPO_PUBLIC_LIVEKIT_TOKEN_SERVER_ID ?? '';
// Which AI agent to invite into the call. Must match AGENT_NAME in agent/chef.py.
const agentName = process.env.EXPO_PUBLIC_AGENT_NAME || 'chef';

interface ConnectionContextType {
  isConfigured: boolean;
  isConnectionActive: boolean;
  connect: () => void;
  disconnect: () => void;
}

const ConnectionContext = createContext<ConnectionContextType>({
  isConfigured: false,
  isConnectionActive: false,
  connect: () => {},
  disconnect: () => {},
});

export function useConnection() {
  return useContext(ConnectionContext);
}

export function ConnectionProvider({ children }: { children: React.ReactNode }) {
  const [isConnectionActive, setIsConnectionActive] = useState(false);

  const tokenSource = useMemo(
    () => TokenSource.developmentTokenServer(tokenServerId),
    []
  );

  const session = useSession(tokenSource, { agentName });
  const { start: startSession, end: endSession } = session;

  const value = useMemo(
    () => ({
      isConfigured: tokenServerId.length > 0,
      isConnectionActive,
      connect: () => {
        setIsConnectionActive(true);
        startSession();
      },
      disconnect: () => {
        setIsConnectionActive(false);
        endSession();
      },
    }),
    [startSession, endSession, isConnectionActive]
  );

  return (
    <SessionProvider session={session}>
      <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>
    </SessionProvider>
  );
}
