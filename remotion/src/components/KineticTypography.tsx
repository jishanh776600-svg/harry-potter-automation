import React from "react";
import { useCurrentFrame } from "remotion";
import { CaptionSegment, TypographyConfig } from "../types/editorialTypes";

interface KineticTypographyProps {
  captions: CaptionSegment[];
  typography: TypographyConfig;
}

export const KineticTypography: React.FC<KineticTypographyProps> = ({
  captions,
  typography,
}) => {
  const frame = useCurrentFrame();

  // Find active caption segment for the current frame
  const activeSegment = captions.find(
    (c) => frame >= c.startFrame && frame <= c.endFrame
  );

  if (!activeSegment) {
    return null;
  }

  return (
    <div
      className="hp-caption-container"
      style={{
        top: activeSegment.positionY || typography.safe_zone_bottom_px,
      }}
    >
      <div className="hp-caption-phrase">
        {activeSegment.words.map((wordObj, idx) => {
          const isWordActive = frame >= wordObj.startFrame;
          const isEmphasized = wordObj.isEmphasized;

          if (!isWordActive) {
            return (
              <span
                key={`${wordObj.word}-${idx}`}
                className="hp-caption-word"
                style={{ opacity: 0.25 }}
              >
                {wordObj.word}
              </span>
            );
          }

          return (
            <span
              key={`${wordObj.word}-${idx}`}
              className={`hp-caption-word ${isEmphasized ? "hp-word-emphasized" : ""}`}
            >
              {wordObj.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
