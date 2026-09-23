import React from "react";
import { interpolate, useCurrentFrame, Video, Img, staticFile } from "remotion";
import { EditorialClipProps } from "../types/editorialTypes";

interface VisualSegmentProps {
  clip: EditorialClipProps;
}

export const VisualSegment: React.FC<VisualSegmentProps> = ({ clip }) => {
  const frame = useCurrentFrame();
  const relFrame = Math.max(0, frame - clip.startFrame);
  const totalFrames = Math.max(1, clip.durationFrames);

  // Compute controlled motion interpolation based on MotionIntent
  let scale = 1.0;
  let translateX = 0;
  let translateY = 0;

  if (clip.motion.intent === "SLOW_PUSH_IN") {
    // Controlled anchor push: 1.00 -> 1.08 smoothly across duration
    scale = interpolate(relFrame, [0, totalFrames], [1.0, 1.08], {
      extrapolateRight: "clamp",
    });
  } else if (clip.motion.intent === "SUBTLE_PUSH") {
    // Subtle reaction push: 1.00 -> 1.04
    scale = interpolate(relFrame, [0, totalFrames], [1.0, 1.04], {
      extrapolateRight: "clamp",
    });
  } else if (clip.motion.intent === "MICRO_PUNCH") {
    // Immediate 1.04 micro punch
    scale = 1.04;
  } else if (clip.motion.intent === "HORIZONTAL_DRIFT") {
    translateX = interpolate(relFrame, [0, totalFrames], [-15, 15], {
      extrapolateRight: "clamp",
    });
  } else if (clip.motion.intent === "VERTICAL_DRIFT") {
    translateY = interpolate(relFrame, [0, totalFrames], [-15, 15], {
      extrapolateRight: "clamp",
    });
  }

  // Fallback if no media exists
  if (!clip.sourcePath || clip.mediaType === "NONE") {
    return (
      <div
        style={{
          width: 1080,
          height: 1920,
          backgroundColor: "#0d0d12",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#888888",
          fontSize: 36,
        }}
      >
        <span>NO_VALID_VISUAL</span>
      </div>
    );
  }

  const transformStyle: React.CSSProperties = {
    width: 1080,
    height: 1920,
    transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
    transformOrigin: clip.isAnchor ? "center center" : "center 40%",
    objectFit: "cover",
  };

  if (clip.mediaType === "IMAGE") {
    return (
      <div style={{ width: 1080, height: 1920, overflow: "hidden" }}>
        <Img src={clip.sourcePath} style={transformStyle} />
      </div>
    );
  }

  return (
    <div style={{ width: 1080, height: 1920, overflow: "hidden" }}>
      <Video src={clip.sourcePath} style={transformStyle} muted />
    </div>
  );
};
