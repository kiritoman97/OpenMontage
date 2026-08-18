export type CinematicTone = "cold" | "steel" | "void" | "neutral";

/**
 * Editorial color intent shared by Remotion and the Resolve conform ledger.
 * This is deliberately semantic: the finishing pass may change exact controls
 * without losing why a shot belongs to a particular look family.
 */
export type CinematicGradeClass =
  | "archive_film"
  | "archival_still"
  | "modern_context"
  | "document_forensic"
  | "memorial_location";

export interface CinematicBaseScene {
  id: string;
  startSeconds: number;
  durationSeconds: number;
  /** Small factual label for archival context; never used as a fallback card. */
  editorialLabel?: string;
  /** Seconds the editorial label remains visible. Omitted = 3 seconds. */
  labelDurationSeconds?: number;
  /** Semantic look family used by Remotion and Resolve finishing. */
  gradeClass?: CinematicGradeClass;
  /** Stable key into the publication credit ledger. */
  creditId?: string;
}

export interface CinematicVideoScene extends CinematicBaseScene {
  kind: "video";
  src: string;
  loop?: boolean;
  tone?: CinematicTone;
  trimBeforeSeconds?: number;
  trimAfterSeconds?: number;
  playbackRate?: number;
  filter?: string;
  fadeInFrames?: number;
  fadeOutFrames?: number;
  /**
   * Per-scene override of the archival film treatment strength.
   * Omitted = inherit the composition-level `archiveLook.intensity`.
   * 0 disables it for this scene -- useful when a clip is genuine archive
   * footage that already carries its own grain and damage.
   */
  archiveIntensity?: number;
}

export interface CinematicTitleScene extends CinematicBaseScene {
  kind: "title";
  text: string;
  accent?: string;
  intensity?: number;
  backgroundSrc?: string;
  backgroundTrimBeforeSeconds?: number;
  backgroundTrimAfterSeconds?: number;
  variant?: "plate" | "overlay";
}

/**
 * Ken Burns move applied to a still. One move per image -- combining a zoom
 * and a pan in different directions reads as drift rather than intent.
 */
export type CinematicImageMove =
  | "zoom-in"
  | "zoom-out"
  | "pan-left"
  | "pan-right"
  | "pan-up"
  | "pan-down"
  | "still";

/**
 * A still photograph or illustration held on screen with a slow move.
 *
 * Needed because much of this material has no filmable subject: archival
 * photographs exist where film does not, and abstract points (documented
 * descent, institutional rules) have no footage at all.
 */
export interface CinematicImageScene extends CinematicBaseScene {
  kind: "image";
  src: string;
  move?: CinematicImageMove;
  /** Scale delta across the scene. 0.06 = a 6% push. Keep it small. */
  moveAmount?: number;
  filter?: string;
  fadeInFrames?: number;
  fadeOutFrames?: number;
  archiveIntensity?: number;
}

export type CinematicScene =
  | CinematicVideoScene
  | CinematicTitleScene
  | CinematicImageScene;

export interface CinematicSoundtrack {
  src: string;
  volume?: number;
  loop?: boolean;
  trimBeforeSeconds?: number;
  trimAfterSeconds?: number;
  fadeInSeconds?: number;
  fadeOutSeconds?: number;
}

/** A narration/audio segment placed at an absolute time on the master timeline. */
export interface CinematicTimedSoundtrack extends CinematicSoundtrack {
  startSeconds: number;
  durationSeconds: number;
}

/** Philosophical documentary end-tag composited over the closing footage. */
export interface CinematicEndTagConfig {
  text: string;
  startSeconds: number;
  durationSeconds: number;
  palette?: "cool_offwhite_on_black" | "warm_ivory_on_black";
  fadeInSeconds?: number;
  holdSeconds?: number;
  fadeOutSeconds?: number;
  fontSize?: number;
  overlayScrimOpacity?: number;
}

export interface CinematicWordCaption {
  word: string;
  startMs: number;
  endMs: number;
}

export interface CinematicCaptionConfig {
  words: CinematicWordCaption[];
  wordsPerPage?: number;
  fontSize?: number;
  color?: string;
  highlightColor?: string;
  backgroundColor?: string;
}

/**
 * Sentence-level subtitles, as opposed to `captions` (which is the
 * word-by-word TikTok-style karaoke overlay). A documentary wants whole
 * readable lines at the bottom of frame, not bouncing words.
 */
export interface CinematicSubtitleCue {
  text: string;
  startSeconds: number;
  endSeconds: number;
}

export interface CinematicSubtitleConfig {
  cues: CinematicSubtitleCue[];
  fontSize?: number;
  color?: string;
  /** Outline around glyphs, in px. 0 disables it. */
  outlineWidth?: number;
  outlineColor?: string;
  fontWeight?: 400 | 500 | 600 | 700;
  /** Backing plate behind the text. Use "none" for no plate. */
  backgroundColor?: string;
  /** Distance from the bottom edge, in px. */
  bottomPx?: number;
  /** Max line width as a fraction of frame width. */
  maxWidthRatio?: number;
}

/** Archival-film treatment applied over every video scene. */
export interface CinematicArchiveLookConfig {
  /** 0 = off (default when the whole block is omitted), 1 = full. */
  intensity?: number;
  grain?: boolean;
  vignette?: boolean;
  dust?: boolean;
  flicker?: boolean;
  gateWeave?: boolean;
  /** Apply the desaturating colour grade to the footage itself. */
  colorGrade?: boolean;
}

export interface CinematicCreditsConfig {
  startSeconds: number;
  heading?: string;
  lines: string[];
}

export interface CinematicRendererProps {
  [key: string]: unknown;
  scenes: CinematicScene[];
  titleFontSize?: number;
  titleWidth?: number;
  signalLineCount?: number;
  soundtrack?: CinematicSoundtrack;
  soundtracks?: CinematicTimedSoundtrack[];
  music?: CinematicSoundtrack;
  captions?: CinematicCaptionConfig;
  subtitles?: CinematicSubtitleConfig;
  archiveLook?: CinematicArchiveLookConfig;
  credits?: CinematicCreditsConfig;
  endTag?: CinematicEndTagConfig;
}
