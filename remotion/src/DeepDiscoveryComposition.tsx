import React from "react";
import { Sequence, AbsoluteFill } from "remotion";
import { DeepDiscoveryProps } from "./types/editorialTypes";
import { VisualSegment } from "./components/VisualSegment";
import { KineticTypography } from "./components/KineticTypography";
import "./styles/typography.css";

export const DeepDiscoveryComposition: React.FC<DeepDiscoveryProps> = ({
  clips,
  typography,
}) => {
  // Collect all captions across clips for continuous caption track
  const allCaptions = clips.flatMap((c) => c.captions);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {/* 1. VISUAL TIMELINE TRACK */}
      {clips.map((clip) => (
        <Sequence
          key={clip.clipId}
          from={clip.startFrame}
          durationInFrames={clip.durationFrames}
        >
          <VisualSegment clip={clip} />
        </Sequence>
      ))}

      {/* 2. KINETIC TYPOGRAPHY CAPTION TRACK */}
      <KineticTypography captions={allCaptions} typography={typography} />
    </AbsoluteFill>
  );
};
