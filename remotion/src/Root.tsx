import React from "react";
import { Composition } from "remotion";
import { DeepDiscoveryComposition } from "./DeepDiscoveryComposition";
import { DeepDiscoveryProps } from "./types/editorialTypes";

const defaultProps: DeepDiscoveryProps = {
  compositionId: "deep_discovery_preview",
  width: 1080,
  height: 1920,
  fps: 30,
  durationInFrames: 2160, // 72 seconds @ 30fps
  clips: [],
  typography: {
    font_family: "Harry P, Georgia, serif",
    font_size_px: 84,
    text_color: "#FFFFFF",
    stroke_color: "#000000",
    stroke_width_px: 4.5,
    margin_v_px: 520,
    margin_h_px: 80,
    safe_zone_bottom_px: 1400,
    max_chars_per_line: 30,
    line_height: 1.15,
    letter_spacing_px: 0.5,
    emphasis_color: "#FFD700",
  },
  fingerprint: "default_preview_fp",
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="DeepDiscoveryShort"
        component={DeepDiscoveryComposition}
        durationInFrames={defaultProps.durationInFrames}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
      />
    </>
  );
};
