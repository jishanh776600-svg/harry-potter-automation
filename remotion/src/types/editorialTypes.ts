/**
 * Remotion Editorial Types & Contracts (Step 4)
 * Synchronized with Python core/editorial_types.py
 */

export type TransitionIntent = "HARD_CUT" | "J_CUT" | "MATCH_CUT" | "CROSSFADE" | "SMASH_CUT";
export type MotionIntent = "NONE" | "SUBTLE_PUSH" | "SLOW_PUSH_IN" | "MICRO_PUNCH" | "HORIZONTAL_DRIFT" | "VERTICAL_DRIFT";
export type EditorialEmphasis = "STANDARD" | "ANCHOR_FOCAL" | "REACTION_INTENSE" | "IRONIC_HIGHLIGHT" | "PAYOFF_RESOLVE";
export type VisualRole = "DIRECT_EVIDENCE" | "CONTEXTUAL_ENVIRONMENT" | "CHARACTER_REACTION" | "IRONIC_CONTRAST";

export interface CaptionWord {
  word: string;
  startFrame: number;
  endFrame: number;
  isEmphasized?: boolean;
}

export interface CaptionSegment {
  segmentId: string;
  text: string;
  startFrame: number;
  endFrame: number;
  positionY: number;
  styleName: string;
  words: CaptionWord[];
}

export interface TransitionSpec {
  intent: TransitionIntent;
  durationFrames: number;
}

export interface MotionSpec {
  intent: MotionIntent;
  emphasis: EditorialEmphasis;
}

export interface EditorialClipProps {
  clipId: string;
  beatId: string;
  sourcePath?: string | null;
  mediaType: "VIDEO" | "IMAGE" | "NONE";
  startFrame: number;
  endFrame: number;
  durationFrames: number;
  visualRole: VisualRole;
  isAnchor: boolean;
  transition: TransitionSpec;
  motion: MotionSpec;
  captions: CaptionSegment[];
}

export interface TypographyConfig {
  font_family: string;
  font_size_px: number;
  text_color: string;
  stroke_color: string;
  stroke_width_px: number;
  margin_v_px: number;
  margin_h_px: number;
  safe_zone_bottom_px: number;
  max_chars_per_line: number;
  line_height: number;
  letter_spacing_px: number;
  emphasis_color: string;
}

export interface DeepDiscoveryProps {
  compositionId: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  clips: EditorialClipProps[];
  typography: TypographyConfig;
  fingerprint: string;
}
