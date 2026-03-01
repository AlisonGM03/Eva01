import { useState, useEffect, useRef } from "react";
import lamejs from "lamejs";

const RecordingIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className="animate-pulse w-full h-full"
  >
    <path d="M8 5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H8Z" />
  </svg>
);

const StopIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className="w-full h-full"
  >
    <path d="M6 18.75a.75.75 0 0 0 .75.75h.75a.75.75 0 0 0 .75-.75V6a.75.75 0 0 0-.75-.75h-.75A.75.75 0 0 0 6 6v12.75ZM16.5 18.75a.75.75 0 0 0 .75.75h.75a.75.75 0 0 0 .75-.75V6a.75.75 0 0 0-.75-.75h-.75a.75.75 0 0 0-.75.75v12.75Z" />
  </svg>
);

const MicIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className="w-full h-full"
  >
    <path d="M8.25 4.5a3.75 3.75 0 1 1 7.5 0v8.25a3.75 3.75 0 1 1-7.5 0V4.5Z" />
    <path d="M6 10.5a.75.75 0 0 1 .75.75v1.5a5.25 5.25 0 1 0 10.5 0v-1.5a.75.75 0 0 1 1.5 0v1.5a6.751 6.751 0 0 1-6 6.709v2.291h3a.75.75 0 0 1 0 1.5h-7.5a.75.75 0 0 1 0-1.5h3v-2.291a6.751 6.751 0 0 1-6-6.709v-1.5A.75.75 0 0 1 6 10.5Z" />
  </svg>
);

const AudioRecorder = ({
  onRecordingComplete,
  disabled,
  isEVATalking,
  cutoffEVA,
  onRecordingStart,
  onRecordingEnd,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const actualDurationRef = useRef(0);
  const timerRef = useRef(null);
  const [recordingError, setRecordingError] = useState(null);

  useEffect(() => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      audioContextRef.current = new AudioCtx({ sampleRate: 16000 });
    }

    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(console.error);
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === "Space") {
        e.preventDefault();

        if (isEVATalking && cutoffEVA) {
          cutoffEVA();
          return;
        }

        if (!isRecording && !disabled) {
          startRecording();
        }
      }
    };

    const handleKeyUp = (e) => {
      if (e.code === "Space" && isRecording) {
        stopRecording();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [isRecording, disabled, isEVATalking]);

  useEffect(() => {
    if (!isRecording) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setRecordingDuration(0);
    }
  }, [isRecording]);

  const startRecording = async () => {
    if (disabled) return;

    setRecordingError(null);

    if (isEVATalking && cutoffEVA) {
      cutoffEVA();
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      setHasPermission(true);

      let mimeType = "audio/wav";
      if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      } else if (MediaRecorder.isTypeSupported("audio/ogg")) {
        mimeType = "audio/ogg";
      }

      console.log(
        `Recording with MIME type: ${mimeType}, sample rate: 16000Hz, mono channel`,
      );

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 128000,
      });

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        } else {
          console.warn("Received empty audio chunk");
        }
      };

      mediaRecorder.onerror = (event) => {
        console.error("MediaRecorder error:", event.error);
        setRecordingError("Recording failed. Please try again.");
        stopRecording();
      };

      actualDurationRef.current = 0;

      mediaRecorder.onstop = async () => {
        if (onRecordingEnd) {
          onRecordingEnd();
        }

        try {
          if (audioChunksRef.current.length === 0) {
            console.warn("No audio chunks recorded");
            setRecordingError("No audio data recorded. Please try again.");
            return;
          }

          const audioBlob = new Blob(audioChunksRef.current, {
            type: mimeType,
          });
          console.log(
            `Recording complete. Blob size: ${audioBlob.size} bytes, type: ${audioBlob.type}`,
          );

          stream.getTracks().forEach((track) => track.stop());

          if (!audioBlob || audioBlob.size < 100) {
            console.warn("Audio recording too small or invalid");
            setRecordingError(
              "Recording too short or invalid. Please try again.",
            );
            return;
          }

          console.log(
            `Actual recording duration: ${actualDurationRef.current.toFixed(1)}s`,
          );
          if (actualDurationRef.current < 0.5) {
            console.warn("Recording too short, ignoring");
            setRecordingError(
              "Recording too short. Please hold for at least 0.5 seconds.",
            );
            return;
          }

          const processedBlob = await processAudioBlob(audioBlob, mimeType);

          if (!processedBlob) {
            console.error("Audio conversion failed, not sending to backend");
            setRecordingError("Audio processing failed. Please try again.");
            return;
          }

          if (onRecordingComplete) {
            onRecordingComplete(processedBlob);
          } else {
            console.error("No callback provided for recording completion");
          }
        } catch (error) {
          console.error("Error processing recording:", error);
          setRecordingError("Error processing recording. Please try again.");
        }
      };

      mediaRecorder.start(500);
      setIsRecording(true);

      if (onRecordingStart) {
        onRecordingStart();
      }

      let duration = 0;
      timerRef.current = setInterval(() => {
        duration += 0.1;
        actualDurationRef.current = duration;
        setRecordingDuration(duration);
      }, 100);
    } catch (error) {
      console.error("Error accessing microphone:", error);

      if (
        error.name === "NotAllowedError" ||
        error.name === "PermissionDeniedError"
      ) {
        setHasPermission(false);
        setRecordingError(
          "Microphone access denied. Please enable microphone access in your browser settings.",
        );
      } else {
        setRecordingError(`Microphone error: ${error.message}`);
      }
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      console.log("Stopping recording...");
      mediaRecorderRef.current.stop();
      setIsRecording(false);

      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  const processAudioBlob = async (blob, originalMimeType) => {
    try {
      console.log(
        `Processing audio blob: size=${blob.size}, type=${originalMimeType}`,
      );

      try {
        const mp3Blob = await convertToMp3(blob);
        console.log(`Converted to MP3 using lamejs: size=${mp3Blob.size}`);
        return mp3Blob;
      } catch (conversionError) {
        console.error("Error converting audio format:", conversionError);
        console.warn("Falling back to original WebM audio format");

        if (originalMimeType === "audio/webm") {
          try {
            console.log("Attempting to convert WebM to WAV as a fallback");
            const wavBlob = await convertToWav(blob);
            return wavBlob;
          } catch (wavError) {
            console.error("Fallback WAV conversion also failed:", wavError);
            return null;
          }
        }

        return null;
      }
    } catch (error) {
      console.error("Error in audio processing:", error);
      return null;
    }
  };

  const convertToWav = async (audioBlob) =>
    new Promise((resolve, reject) => {
      try {
        console.log("Converting audio to WAV format as fallback...");

        const audioContext = new (
          window.AudioContext || window.webkitAudioContext
        )({
          sampleRate: 16000,
        });

        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const audioData = await audioContext.decodeAudioData(reader.result);

            const numberOfChannels = 1;
            const sampleRate = 16000;
            const length = audioData.length;

            const offlineContext = new OfflineAudioContext(
              numberOfChannels,
              length,
              sampleRate,
            );
            const bufferSource = offlineContext.createBufferSource();
            bufferSource.buffer = audioData;
            bufferSource.connect(offlineContext.destination);
            bufferSource.start(0);

            const renderedBuffer = await offlineContext.startRendering();
            const wavBlob = bufferToWav(renderedBuffer);
            console.log(`Converted audio to WAV: ${wavBlob.size} bytes`);
            audioContext.close();
            resolve(wavBlob);
          } catch (decodingError) {
            console.error(
              "Error decoding audio data for WAV conversion:",
              decodingError,
            );
            reject(decodingError);
          }
        };

        reader.onerror = (error) => {
          console.error("Error reading audio blob for WAV conversion:", error);
          reject(error);
        };

        reader.readAsArrayBuffer(audioBlob);
      } catch (error) {
        console.error("Error in WAV conversion:", error);
        reject(error);
      }
    });

  const bufferToWav = (buffer) => {
    const numberOfChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const length = buffer.length * numberOfChannels * 2;
    const arrayBuffer = new ArrayBuffer(44 + length);
    const view = new DataView(arrayBuffer);

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + length, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numberOfChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numberOfChannels * 2, true);
    view.setUint16(32, numberOfChannels * 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, "data");
    view.setUint32(40, length, true);

    const offset = 44;
    for (let i = 0; i < buffer.numberOfChannels; i++) {
      const channelData = buffer.getChannelData(i);
      let pos = offset;

      for (let j = 0; j < channelData.length; j++, pos += 2) {
        const sample = Math.max(-1, Math.min(1, channelData[j]));
        view.setInt16(
          pos,
          sample < 0 ? sample * 0x8000 : sample * 0x7fff,
          true,
        );
      }
    }

    return new Blob([view], { type: "audio/wav" });
  };

  const writeString = (view, offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  const convertToMp3 = async (audioBlob) =>
    new Promise((resolve, reject) => {
      try {
        console.log("Converting audio to MP3 format using lamejs...");

        const audioContext = new (
          window.AudioContext || window.webkitAudioContext
        )({
          sampleRate: 16000,
        });

        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const audioData = await audioContext.decodeAudioData(reader.result);

            const sampleRate = 16000;
            const channels = 1;
            const kbps = 128;
            const mp3encoder = new lamejs.Mp3Encoder(
              channels,
              sampleRate,
              kbps,
            );
            const pcmData = audioData.getChannelData(0);

            const samples = new Int16Array(pcmData.length);
            for (let i = 0; i < pcmData.length; i++) {
              samples[i] = Math.max(-1, Math.min(1, pcmData[i])) * 32767.5;
            }

            const data = [];
            const sampleBlockSize = 1152;
            for (let i = 0; i < samples.length; i += sampleBlockSize) {
              const chunk = samples.subarray(i, i + sampleBlockSize);
              const mp3buf = mp3encoder.encodeBuffer(chunk);
              if (mp3buf.length > 0) {
                data.push(mp3buf);
              }
            }

            const mp3buf = mp3encoder.flush();
            if (mp3buf.length > 0) {
              data.push(mp3buf);
            }

            const mp3Blob = new Blob(data, { type: "audio/mp3" });
            console.log(`MP3 encoding complete: size=${mp3Blob.size} bytes`);
            audioContext.close();
            resolve(mp3Blob);
          } catch (decodingError) {
            console.error("Error decoding audio data:", decodingError);
            reject(decodingError);
          }
        };

        reader.onerror = (error) => {
          console.error("Error reading audio blob for MP3 conversion:", error);
          reject(error);
        };

        reader.readAsArrayBuffer(audioBlob);
      } catch (error) {
        console.error("Error in MP3 conversion:", error);
        reject(error);
      }
    });

  const formatTime = (seconds) => `${seconds.toFixed(1)}s`;

  const getButtonLabel = () => {
    if (isRecording) return `Recording ${formatTime(recordingDuration)}`;
    if (isEVATalking) return "Press space to stop";
    return "Hold space to speak";
  };

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <div
          className={`flex items-center justify-center space-x-2 px-5 py-3
            border border-opacity-25 backdrop-blur-sm rounded-full
            ${
              isRecording
                ? "bg-red-500/15 border-red-400 shadow-sm shadow-red-900/10"
                : isEVATalking
                  ? "bg-blue-500/15 border-blue-400 shadow-sm shadow-blue-900/10"
                  : "bg-blue-500/10 border-blue-400 shadow-sm shadow-blue-900/10"
            }
            transition-all duration-300
          `}
        >
          <div
            className={`w-6 h-6 mr-2 ${isRecording || isEVATalking ? "text-red-300" : "text-blue-300"}`}
          >
            {isRecording ? (
              <RecordingIcon />
            ) : isEVATalking ? (
              <StopIcon />
            ) : (
              <MicIcon />
            )}
          </div>
          <span
            className={`text-base ${isRecording || isEVATalking ? "text-red-300" : "text-blue-300"}`}
          >
            {getButtonLabel()}
          </span>
        </div>
      </div>

      {recordingError && (
        <div className="text-red-400 text-xs mt-2 max-w-xs text-center">
          {recordingError}
        </div>
      )}
    </div>
  );
};

export default AudioRecorder;
