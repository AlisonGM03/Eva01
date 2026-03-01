import { useEffect, useState } from "react";

const EVAAnimation = ({ isActive, mode = "default" }) => {
  const totalBars = 12;
  const [barHeights, setBarHeights] = useState([]);

  useEffect(() => {
    const heights = Array(totalBars)
      .fill()
      .map(() => Math.floor(Math.random() * 6) + 3);
    setBarHeights(heights);
  }, []);

  if (mode === "processing") {
    return (
      <div className="relative w-full max-w-xs mx-auto h-20 flex items-center justify-center">
        <div className="absolute w-20 h-20 rounded-full bg-blue-400 opacity-15 blur-md animate-pulse scale-110"></div>
      </div>
    );
  }

  return (
    <div className="relative w-full max-w-xs mx-auto h-20 flex items-center justify-center">
      <div
        className={`absolute w-16 h-16 rounded-full
        ${isActive ? "bg-blue-400 opacity-15" : "bg-blue-300 opacity-10"}
        blur-md transition-all duration-500
        ${isActive ? "scale-110" : "scale-100"}`}
      ></div>

      <div className="flex items-center justify-center h-12 gap-[3px] z-10">
        {[...Array(totalBars)].map((_, index) => (
          <div
            key={index}
            className={`w-1 rounded-full transition-all duration-300
              ${
                isActive
                  ? "bg-blue-400 bg-opacity-70 animate-wave"
                  : "bg-blue-300 bg-opacity-40"
              }`}
            style={{
              height: isActive ? undefined : `${barHeights[index] || 3}px`,
              animationDelay: `${index * 70}ms`,
            }}
          />
        ))}
      </div>
    </div>
  );
};

const styles = `
  @keyframes wave {
    0% { height: 3px; }
    50% { height: 25px; }
    100% { height: 5px; }
  }

  .animate-wave {
    animation: wave 1.5s ease-in-out infinite;
  }
`;

const styleElement = document.createElement("style");
styleElement.innerHTML = styles;
document.head.appendChild(styleElement);

export default EVAAnimation;
