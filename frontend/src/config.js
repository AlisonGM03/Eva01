/**
 * EVA App Configuration
 * Central configuration file for the EVA React application
 */

const config = {
  websocket: {
    baseUrl: import.meta.env.VITE_EVA_WS_URL || "ws://localhost:8080",
    reconnectInterval: 3000,
    reconnectAttempts: 5,
  },
  api: {
    baseUrl: import.meta.env.VITE_EVA_API_URL || "http://localhost:8080",
    downloadPath: "/download",
  },
  behavior: {
    imageQuality: 0.92,
    audioEnabled: true,
    ttsEnabled: true,
    captions: true,
  },
  app: {
    name: import.meta.env.VITE_APP_NAME || "EVA Voice Assistant",
    version: "1.0.0",
  },
  debug: {
    verbose: import.meta.env.DEV,
    logWebSocketMessages: import.meta.env.DEV,
    logAudioOperations: true,
    showAudioUrls: true,
    showAllDebug: import.meta.env.DEV,
    enabled: import.meta.env.DEV,
  },
};

export default config;
