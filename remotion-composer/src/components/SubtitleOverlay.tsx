import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont } from "@remotion/google-fonts/SpaceGrotesk";
import { CinematicSubtitleConfig } from "../cinematic/types";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600"],
  subsets: ["latin"],
});

/**
 * Sentence-level documentary subtitles.
 *
 * Distinct from CaptionOverlay, which is the word-by-word karaoke style used
 * for social video. Here each cue is a whole readable line timed to the
 * narration.
 *
 * Legibility without a plate
 * --------------------------
 * The default style deliberately has NO background box. A hard rectangle
 * fights the archival film treatment -- it reads as a modern UI element
 * pasted over aged footage. Instead the text is separated from the picture
 * by three stacked shadows: a tight dark contact shadow, a wider soft one,
 * and a broad glow. That is what broadcast subtitles do, and it survives
 * both bright and dark backgrounds without ever drawing a visible edge.
 *
 * Pass backgroundColor explicitly if a plate is genuinely wanted.
 */
export const SubtitleOverlay: React.FC<CinematicSubtitleConfig> = ({
  cues,
  fontSize = 46,
  color = "#F7F4ED",
  outlineWidth = 1.8,
  outlineColor = "#070605",
  fontWeight = 700,
  backgroundColor = "none",
  bottomPx = 110,
  maxWidthRatio = 0.78,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const seconds = frame / fps;

  const active = cues.find(
    (cue) => seconds >= cue.startSeconds && seconds < cue.endSeconds,
  );
  if (!active) return null;

  // Short cross-fade at each end so lines don't pop. Kept well under the
  // minimum cue length so it never eats a whole cue.
  const FADE = 0.14;
  const intoCue = seconds - active.startSeconds;
  const untilEnd = active.endSeconds - seconds;
  const opacity = Math.min(
    1,
    Math.max(0, intoCue / FADE),
    Math.max(0, untilEnd / FADE),
  );

  const hasPlate = backgroundColor !== "none" && backgroundColor !== undefined;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        pointerEvents: "none",
        paddingBottom: bottomPx,
      }}
    >
      {/* Very soft luminance lift behind the text only -- no hard edge.
          This is what keeps white text readable over a bright sky without
          drawing a box. Radial so it has no boundary at all. */}
      {hasPlate ? null : (
        <div
          style={{
            position: "absolute",
            bottom: bottomPx - fontSize * 0.9,
            width: width * (maxWidthRatio + 0.14),
            height: fontSize * 3.2,
            background:
              "radial-gradient(ellipse at center, rgba(0,0,0,0.42) 0%," +
              " rgba(0,0,0,0.22) 45%, rgba(0,0,0,0) 78%)",
            opacity,
          }}
        />
      )}
      <div
        style={{
          maxWidth: width * maxWidthRatio,
          padding: hasPlate ? "14px 26px" : 0,
          borderRadius: hasPlate ? 6 : undefined,
          background: hasPlate ? backgroundColor : undefined,
          fontFamily,
          fontWeight,
          fontSize,
          lineHeight: 1.32,
          letterSpacing: "0.008em",
          color,
          textAlign: "center",
          WebkitTextStroke:
            outlineWidth > 0
              ? outlineWidth + "px " + outlineColor
              : undefined,
          // Three stacked shadows: tight contact, soft spread, wide glow.
          // Together they read as separation from the picture without any
          // visible container.
          textShadow: [
            "0 1px 1px rgba(0,0,0,1)",
            "0 2px 8px rgba(0,0,0,0.95)",
            "0 0 24px rgba(0,0,0,0.72)",
          ].join(", "),
          opacity,
        }}
      >
        {active.text}
      </div>
    </AbsoluteFill>
  );
};
