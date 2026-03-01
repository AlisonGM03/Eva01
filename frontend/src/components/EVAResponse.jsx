import { useState, useEffect, useRef } from "react";
import EVAAnimation from "./EVAAnimation";
import AudioRecorder from "./AudioRecorder";
import webSocketService from "../services/WebSocketService";
import config from "../config";

const EVAResponse = ({ query, onReset }) => {
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isEVATalking, setIsEVATalking] = useState(false);
  const audioRef = useRef(null);
  const [htmlContent, setHtmlContent] = useState(null);
  const audioQueue = useRef([]);
  const [speechText, setSpeechText] = useState("");
  const [speechVisible, setSpeechVisible] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isWaitingForUserInput, setIsWaitingForUserInput] = useState(false);
  const lastAudioPlayedTime = useRef(null);
  const [userSpeaking, setUserSpeaking] = useState(false);

  const getStatusLabel = () => {
    if (isLoading) return { text: "Processing", color: "yellow" };
    if (isEVATalking) return { text: "Speaking", color: "blue" };
    if (userSpeaking) return { text: "Listening", color: "red" };
    if (isWaitingForUserInput) return { text: "Ready", color: "green" };
    return { text: "Connecting", color: "gray" };
  };

  const debugLog = (message, type = "info") => {
    if (config.debug.logAudioOperations) {
      console.log(`[EVA-${type}] ${message}`);
    }
  };

  useEffect(() => {
    setIsEVATalking(false);
    debugLog("Component mounted, reset EVA talking state to false");

    webSocketService.setConnectionStatusCallback((status) => {
      setIsConnected(status === "connected");
      if (status === "connected") {
        setIsLoading(false);
        setIsWaitingForUserInput(true);
      }
    });

    webSocketService.connect().catch((error) => {
      console.error("Failed to connect to WebSocket:", error);
      setResponse(
        "Sorry, I encountered an error connecting to EVA. Please try again later.",
      );
      setIsLoading(false);
    });

    webSocketService.setMessageCallback(handleWebSocketMessage);

    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
      webSocketService.setMessageCallback(null);
      webSocketService.setConnectionStatusCallback(null);
    };
  }, []);

  useEffect(() => {
    if (query && !isLoading && !response && isConnected) {
      sendQueryViaWebSocket(query);
    } else if (query && !isConnected) {
      setResponse("Waiting for connection to EVA server. Please wait...");
    }
  }, [query, isConnected, isLoading, response]);

  useEffect(() => {
    if (audioQueue.current.length > 0 && !isEVATalking) {
      const nextAudio = audioQueue.current.shift();
      setTimeout(() => {
        playAudio(nextAudio);
      }, 50);
    }
  }, [isEVATalking]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      if (isEVATalking && audioRef.current) {
        if (audioRef.current.paused || audioRef.current.ended) {
          debugLog(
            "Audio is paused or ended but isEVATalking=true. Resetting state.",
            "warning",
          );
          setIsEVATalking(false);
        }
      }
    }, 2000);

    if (isEVATalking && lastAudioPlayedTime.current) {
      const timeSinceLastAudio = Date.now() - lastAudioPlayedTime.current;
      if (timeSinceLastAudio > 10000) {
        debugLog(
          `Talking state appears stuck for ${timeSinceLastAudio}ms. Resetting to false.`,
          "warning",
        );
        setIsEVATalking(false);
      }
    }

    return () => clearInterval(intervalId);
  }, [isEVATalking]);

  const handleWebSocketMessage = (message) => {
    if (!message) return;
    console.log("Processing message:", message);

    if (message.type === "audio") {
      const audioUrl = message.content;
      if (message.text) {
        setSpeechText(message.text);
        setResponse(message.text);
      }

      audioQueue.current.push(audioUrl);

      if (!isEVATalking) {
        const nextAudio = audioQueue.current.shift();
        if (
          nextAudio &&
          typeof nextAudio === "string" &&
          nextAudio.trim() !== ""
        ) {
          setTimeout(() => {
            playAudio(nextAudio);
          }, 50);
        }
      }

      setIsLoading(false);
      return;
    }

    if (message.type === "html") {
      setHtmlContent(message.content);
      setIsLoading(false);
      return;
    }

    if (message.type === "over") {
      if (message.content) {
        webSocketService.sessionId = message.content;
      }
      setIsLoading(false);
      setIsWaitingForUserInput(true);
      return;
    }

    if (message.wait === true) {
      setIsWaitingForUserInput(true);
      setIsLoading(false);
      return;
    }

    if (message.speech) {
      setSpeechText(message.speech);
      setResponse(message.speech);
      setIsLoading(false);
      return;
    }

    if (message.text) {
      setSpeechText(message.text);
      setResponse(message.text);
      setIsLoading(false);
      return;
    }

    if (message.response) {
      setResponse(message.response);
      setIsLoading(false);
    }
  };

  const sendQueryViaWebSocket = async (queryText) => {
    try {
      await webSocketService.sendMessage(queryText);
    } catch (error) {
      console.error("Error sending query via WebSocket:", error);
      setResponse(
        "Sorry, I encountered an error while processing your request.",
      );
      setIsLoading(false);
    }
  };

  const handleAudioRecorded = async (audioBlob) => {
    if (isLoading) return;

    setIsWaitingForUserInput(false);
    setIsLoading(true);
    setUserSpeaking(false);
    setResponse("");
    setSpeechText("");
    setHtmlContent(null);
    setIsEVATalking(false);
    audioQueue.current = [];

    try {
      if (!audioBlob) throw new Error("No audio data received");
      if (audioBlob.size === 0)
        throw new Error("Empty audio recording received");

      if (audioBlob.size < 1000) {
        setResponse(
          "Processing your message... (Warning: short audio detected)",
        );
      } else {
        setResponse("Processing your message...");
      }

      await webSocketService.sendAudio(audioBlob);

      const messageTimeout = setTimeout(() => {
        if (isLoading) {
          setIsLoading(false);
          setResponse(
            "The server is taking longer than expected to respond. Please try again or try a different message.",
          );
        }
      }, 15000);

      return () => clearTimeout(messageTimeout);
    } catch (error) {
      console.error("Error processing speech:", error);
      setIsLoading(false);

      let errorMessage;
      if (!error) {
        errorMessage =
          "An unknown error occurred while processing your speech.";
      } else if (error.name === "NotAllowedError") {
        errorMessage =
          "Microphone access is required. Please grant permission in your browser settings.";
      } else if (error.message?.includes("audio format")) {
        errorMessage =
          "Your audio format is not supported. Please try again with a different device or browser.";
      } else if (error.message?.includes("convert")) {
        errorMessage =
          "Could not process the audio data. Please try speaking more clearly or use a better microphone.";
      } else if (
        error.message?.includes("empty") ||
        error.message?.includes("short")
      ) {
        errorMessage =
          "Your recording was too short or empty. Please hold the button and speak clearly.";
      } else if (
        error.message?.includes("connect") ||
        error.message?.includes("Communication")
      ) {
        errorMessage =
          "Could not connect to the server. Please check your internet connection and try again.";
      } else {
        errorMessage = `Error: ${error.message || "Failed to process speech. Please try again."}`;
      }

      setResponse(errorMessage);
    }
    return undefined;
  };

  const playAudio = (audioUrl) => {
    if (!audioUrl) {
      setIsEVATalking(false);
      return;
    }

    if (typeof audioUrl !== "string" || audioUrl.trim() === "") {
      setIsEVATalking(false);
      return;
    }

    lastAudioPlayedTime.current = Date.now();
    setIsEVATalking(true);

    if (audioRef.current) {
      try {
        audioRef.current.pause();
        audioRef.current.src = "";
        audioRef.current = null;
      } catch (e) {
        debugLog(`Error cleaning up previous audio: ${e.message}`, "error");
      }
    }

    // audioUrl is already formatted by WebSocketService
    const cacheBustUrl = audioUrl;
    if (!config.behavior.audioEnabled) {
      setIsEVATalking(false);
      return;
    }

    fetch(cacheBustUrl, {
      method: "GET",
      headers: {
        Accept: "audio/mpeg, audio/*",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        Pragma: "no-cache",
        Expires: "0",
      },
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error! Status: ${res.status}`);
        }
        return res.blob();
      })
      .then((blob) => {
        if (blob.size === 0) {
          throw new Error("Empty audio blob received");
        }

        const objectUrl = URL.createObjectURL(blob);
        const audio = new Audio();
        audioRef.current = audio;

        audio.addEventListener("play", () => {
          setIsEVATalking(true);
          if (config.behavior.captions && speechText) {
            setSpeechVisible(true);
          }
        });

        audio.addEventListener("ended", () => {
          setIsEVATalking(false);
          setSpeechVisible(false);
          URL.revokeObjectURL(objectUrl);
          if (audioQueue.current.length > 0) {
            const nextAudio = audioQueue.current.shift();
            setTimeout(() => playAudio(nextAudio), 300);
          }
        });

        audio.addEventListener("error", () => {
          URL.revokeObjectURL(objectUrl);
          setIsEVATalking(false);
        });

        audio.crossOrigin = "anonymous";
        audio.preload = "auto";
        audio.src = objectUrl;
        audio.play().catch(() => {
          URL.revokeObjectURL(objectUrl);
          setIsEVATalking(false);
        });
      })
      .catch((error) => {
        console.error(
          "Failed to fetch or process audio file:",
          error,
          cacheBustUrl,
        );
        setIsEVATalking(false);
      });
  };

  const cutoffEVA = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsEVATalking(false);
    }
  };

  const handleReset = () => {
    cutoffEVA();
    setResponse("");
    setSpeechText("");
    setHtmlContent(null);
    setIsLoading(false);
    onReset();
  };

  const showSpaceButton = !isLoading || isWaitingForUserInput || isEVATalking;
  const status = getStatusLabel();
  const statusClassMap = {
    yellow: "bg-yellow-500 text-yellow-300",
    blue: "bg-blue-500 text-blue-300",
    red: "bg-red-500 text-red-300",
    green: "bg-green-500 text-green-300",
    gray: "bg-gray-500 text-gray-300",
  };
  const statusClasses = statusClassMap[status.color] || statusClassMap.gray;

  return (
    <div className="w-full">
      <div className="w-full p-4 transition-all duration-300">
        <div className="flex items-center justify-between mb-4">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-sm font-medium bg-opacity-20 ${statusClasses}`}
          >
            {status.text === "Ready" && (
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-ping mr-1.5"></span>
            )}
            {status.text}
          </span>
        </div>

        <div className="flex flex-col items-center min-h-[280px] relative">
          {isLoading && (
            <div className="flex flex-col items-center justify-center h-full">
              <EVAAnimation isActive mode="processing" />
            </div>
          )}

          {(response || htmlContent) && !isLoading && (
            <div className="w-full mt-2 text-center px-4">
              {query && (
                <div className="mb-2">
                  <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-1">
                    You
                  </h3>
                  <p className="text-gray-300 text-sm">{query}</p>
                </div>
              )}

              <div className="text-gray-200 mt-2">
                {htmlContent ? (
                  <div
                    className="text-gray-200 overflow-auto max-h-96"
                    dangerouslySetInnerHTML={{ __html: htmlContent }}
                  />
                ) : (
                  <p className="text-gray-200 whitespace-pre-wrap text-center">
                    {response}
                  </p>
                )}
              </div>
            </div>
          )}

          {isWaitingForUserInput && !isLoading && !response && !htmlContent && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="transform scale-75">
                <EVAAnimation isActive={false} />
              </div>
              <p className="text-gray-400 mt-2 text-sm">Press space to speak</p>
            </div>
          )}

          {showSpaceButton && (
            <div className="absolute bottom-2">
              <AudioRecorder
                onRecordingComplete={handleAudioRecorded}
                disabled={isLoading && !isEVATalking}
                isEVATalking={isEVATalking}
                cutoffEVA={cutoffEVA}
                onRecordingStart={() => setUserSpeaking(true)}
                onRecordingEnd={() => setUserSpeaking(false)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EVAResponse;
