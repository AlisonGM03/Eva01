import { useState, useRef, useEffect } from "react";
import webSocketService from "../services/WebSocketService";
import config from "../config";

const drawOverlay = (
  context,
  canvasWidth,
  canvasHeight,
  isFrontImage,
  isFallback = false,
) => {
  const timestamp = new Date().toLocaleString();
  const imageTypeLabel = isFrontImage ? "Observation" : "View";

  if (isFallback) {
    context.fillStyle = "#f0f0f0";
    context.fillRect(0, 0, canvasWidth, canvasHeight);

    context.fillStyle = "#333333";
    context.font = "24px Arial";
    context.textAlign = "center";
    context.fillText(
      "Camera not available",
      canvasWidth / 2,
      canvasHeight / 2 - 20,
    );
    context.fillText(
      isFrontImage ? "Using fallback front image" : "Using fallback back image",
      canvasWidth / 2,
      canvasHeight / 2 + 20,
    );
  }

  // Draw Timestamp
  context.fillStyle = isFallback ? "black" : "rgba(255, 255, 255, 0.7)";
  if (!isFallback) context.fillRect(10, 10, 200, 20);
  context.fillStyle = "black";
  context.font = "12px Arial";
  context.textAlign = "left";
  context.fillText(
    `${isFallback ? "Generated" : "Captured"}: ${timestamp}`,
    15,
    25,
  );

  // Draw Image Type Label
  context.fillStyle = "rgba(0, 0, 0, 0.5)";
  context.fillRect(canvasWidth - 100, 10, 90, 20);
  context.fillStyle = "white";
  context.textAlign = "right";
  context.fillText(imageTypeLabel, canvasWidth - 15, 25);
  context.textAlign = "left";
};

const VideoCapture = ({ onImageCaptured }) => {
  const [cameraStatus, setCameraStatus] = useState("initializing");
  const [errorMessage, setErrorMessage] = useState("");
  const [isCapturing, setIsCapturing] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      initializeCamera();
    }, 1000);

    return () => {
      clearTimeout(timer);
      stopCamera();
    };
  }, []);

  useEffect(() => {
    console.log("Setting up image request handler in VideoCapture");
    const handleImageRequest = (requestType) => {
      console.log(
        `CRITICAL: Backend requested an image capture: ${requestType || "frontImage"}`,
      );

      if (cameraStatus === "success" && !isCapturing) {
        const isFrontImage = !requestType || requestType === "frontImage";
        console.log(
          `CRITICAL: Camera available, capturing ${isFrontImage ? "frontImage" : "backImage"}`,
        );
        captureAndSendImage(isFrontImage);
      } else if (cameraStatus === "error") {
        const isFrontImage = !requestType || requestType === "frontImage";
        console.log(
          `CRITICAL: Camera unavailable, creating fallback ${isFrontImage ? "frontImage" : "backImage"}`,
        );
        createFallbackImage(isFrontImage);
      } else {
        console.log(
          `CRITICAL: Cannot capture image - Camera status: ${cameraStatus}, isCapturing: ${isCapturing}`,
        );
      }
    };

    webSocketService.setImageRequestCallback(handleImageRequest);
    console.log(
      "CRITICAL: Image request handler registered with WebSocketService",
    );

    return () => {
      console.log("Clearing image request handler");
      webSocketService.setImageRequestCallback(null);
    };
  }, [cameraStatus, isCapturing]);

  useEffect(() => {
    if (cameraStatus === "success" && !isCapturing) {
      console.log("Camera is now ready, sending initial image");
      setTimeout(() => {
        captureAndSendImage(true);
      }, 1000);
    }
  }, [cameraStatus, isCapturing]);

  const initializeCamera = async () => {
    try {
      const constraints = {
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          setCameraStatus("success");
        };
      }
    } catch (error) {
      console.error("Camera initialization error:", error);
      setCameraStatus("error");
      setErrorMessage(error.message || "Could not access camera");
      createFallbackImage();
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      const tracks = streamRef.current.getTracks();
      tracks.forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  };

  const captureAndSendImage = (isFrontImage = true) => {
    if (cameraStatus !== "success" || !videoRef.current || !canvasRef.current) {
      console.error(`CRITICAL: Cannot capture image - prerequisites not met:
        - cameraStatus: ${cameraStatus}
        - videoRef: ${videoRef.current ? "available" : "not available"}
        - canvasRef: ${canvasRef.current ? "available" : "not available"}`);
      return;
    }

    console.log("CRITICAL: Starting image capture process");
    setIsCapturing(true);

    try {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      drawOverlay(context, canvas.width, canvas.height, isFrontImage, false);

      console.log("CRITICAL: Canvas image prepared, converting to blob");
      canvas.toBlob(
        (blob) => {
          console.log(
            `CRITICAL: Canvas converted to blob: ${blob.size} bytes. Sending to WebSocketService.`,
          );
          webSocketService.sendImage(blob, isFrontImage);

          if (onImageCaptured && typeof onImageCaptured === "function") {
            const imageUrl = URL.createObjectURL(blob);
            onImageCaptured(imageUrl, isFrontImage ? "observation" : "view");
          }

          setTimeout(() => {
            setIsCapturing(false);
          }, 500);
        },
        "image/jpeg",
        config.behavior.imageQuality,
      );
    } catch (error) {
      console.error("CRITICAL ERROR: Failed capturing image:", error);
      setIsCapturing(false);
    }
  };

  const createFallbackImage = (isFrontImage = true) => {
    if (!canvasRef.current) {
      return;
    }

    try {
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");

      canvas.width = 640;
      canvas.height = 480;
      drawOverlay(context, canvas.width, canvas.height, isFrontImage, true);

      canvas.toBlob(
        (blob) => {
          console.log(
            `Sending fallback ${isFrontImage ? "frontImage" : "backImage"} to backend`,
          );
          webSocketService.sendImage(blob, isFrontImage);

          if (onImageCaptured && typeof onImageCaptured === "function") {
            const imageUrl = URL.createObjectURL(blob);
            onImageCaptured(imageUrl, isFrontImage ? "observation" : "view");
          }
        },
        "image/jpeg",
        config.behavior.imageQuality,
      );
    } catch (error) {
      console.error("Error creating fallback image:", error);
    }
  };

  return (
    <div className="relative">
      {cameraStatus === "initializing" && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-800 bg-opacity-50 text-white z-10">
          Initializing camera...
        </div>
      )}

      {cameraStatus === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-800 bg-opacity-75 text-white z-10 p-4">
          <p className="text-red-400 font-semibold">Camera Error</p>
          <p className="text-sm">{errorMessage}</p>
          <p className="text-xs mt-2">Using fallback images</p>
        </div>
      )}

      <video
        ref={videoRef}
        className={`w-full h-auto rounded-lg ${cameraStatus !== "success" ? "opacity-50" : ""}`}
        autoPlay
        playsInline
        muted
      />

      <canvas ref={canvasRef} className="hidden" />

      {isCapturing && (
        <div className="absolute top-2 right-2 bg-blue-500 text-white text-xs px-2 py-1 rounded">
          Capturing...
        </div>
      )}
    </div>
  );
};

export default VideoCapture;
