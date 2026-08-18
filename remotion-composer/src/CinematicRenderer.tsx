import React from "react";
import { loadFont } from "@remotion/google-fonts/SpaceGrotesk";
import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Loop,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { CinematicRendererProps, CinematicTone, CinematicVideoScene } from "./cinematic/types";
import { CaptionOverlay } from "./components/CaptionOverlay";
import { resolveAsset } from "./lib/resolveAsset";
import { SubtitleOverlay } from "./components/SubtitleOverlay";
import { SceneImage } from "./components/SceneImage";
import { EndTag } from "./components/EndTag";
import {
  ArchiveFilmLook,
  archiveFilmFilter,
  gateWeaveOffset,
} from "./components/ArchiveFilmLook";
import { CinematicArchiveLookConfig } from "./cinematic/types";

const FPS = 30;

const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "700"],
  subsets: ["latin"],
});

const toneGradient = (tone: CinematicTone) => {
  switch (tone) {
    case "steel":
      return "linear-gradient(180deg, rgba(6,12,18,0.18) 0%, rgba(2,4,8,0.48) 100%)";
    case "void":
      return "linear-gradient(180deg, rgba(2,4,8,0.14) 0%, rgba(0,0,0,0.56) 100%)";
    case "neutral":
      return "linear-gradient(180deg, rgba(10,10,12,0.16) 0%, rgba(0,0,0,0.42) 100%)";
    case "cold":
    default:
      return "linear-gradient(180deg, rgba(8,16,24,0.18) 0%, rgba(2,4,8,0.42) 100%)";
  }
};

const SceneVideo: React.FC<{
  scene: CinematicVideoScene;
  archiveLook?: CinematicArchiveLookConfig;
}> = ({ scene, archiveLook }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationInFrames = Math.max(1, Math.round(scene.durationSeconds * fps));
  const fadeInFrames = scene.fadeInFrames ?? 10;
  const fadeOutFrames = scene.fadeOutFrames ?? 10;
  const fadeOutStart = Math.max(0, durationInFrames - fadeOutFrames);
  const fadeInOpacity =
    fadeInFrames === 0
      ? 1
      : interpolate(frame, [0, fadeInFrames], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const fadeOutOpacity =
    fadeOutFrames === 0
      ? 1
      : interpolate(frame, [fadeOutStart, durationInFrames], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const opacity = Math.min(fadeInOpacity, fadeOutOpacity);

  const scale = interpolate(frame, [0, durationInFrames], [1.015, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const trimBefore =
    scene.trimBeforeSeconds !== undefined
      ? Math.round(scene.trimBeforeSeconds * fps)
      : undefined;
  const trimAfter =
    scene.trimAfterSeconds !== undefined
      ? Math.round(scene.trimAfterSeconds * fps)
      : undefined;
  const loopDuration = Math.max(
    1,
    (trimAfter ?? durationInFrames) - (trimBefore ?? 0),
  );

  // Archive treatment. Per-scene `archiveIntensity` wins over the
  // composition-level setting so genuine archive footage (which already has
  // its own grain and damage) can opt out with 0.
  const archiveIntensity =
    scene.archiveIntensity ?? archiveLook?.intensity ?? 0;
  const archiveOn = archiveIntensity > 0;
  const weave =
    archiveOn && archiveLook?.gateWeave !== false
      ? gateWeaveOffset(frame, archiveIntensity)
      : 0;

  // An explicit per-scene `filter` always wins -- it is a manual override.
  // Otherwise, when grading is on, use the archival chain; else the default.
  const videoFilter =
    scene.filter ??
    (archiveOn && archiveLook?.colorGrade !== false
      ? archiveFilmFilter(archiveIntensity)
      : "contrast(1.06) saturate(0.88) brightness(0.92)");

  return (
    <AbsoluteFill style={{ backgroundColor: "#020407", opacity }}>
      {scene.loop ? (
        <Loop durationInFrames={loopDuration}>
          <OffthreadVideo
            muted
            src={resolveAsset(scene.src)}
            trimBefore={trimBefore}
            trimAfter={trimAfter}
            playbackRate={scene.playbackRate}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${archiveOn ? scale + 0.004 : scale}) translateY(${weave}px)`,
              filter: videoFilter,
            }}
          />
        </Loop>
      ) : (
        <OffthreadVideo
          muted
          src={resolveAsset(scene.src)}
          trimBefore={trimBefore}
          trimAfter={trimAfter}
          playbackRate={scene.playbackRate}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${archiveOn ? scale + 0.004 : scale}) translateY(${weave}px)`,
            filter: videoFilter,
          }}
        />
      )}
      <AbsoluteFill
        style={{
          background: toneGradient(scene.tone ?? "cold"),
          mixBlendMode: "multiply",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.52) 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 8%, transparent 92%, rgba(255,255,255,0.02) 100%)",
          opacity: 0.6,
        }}
      />
      {archiveOn ? (
        <ArchiveFilmLook
          intensity={archiveIntensity}
          grain={archiveLook?.grain}
          vignette={archiveLook?.vignette}
          dust={archiveLook?.dust}
          flicker={archiveLook?.flicker}
          seed={scene.id}
        />
      ) : null}
    </AbsoluteFill>
  );
};

const SignalTexture: React.FC<{
  accent: string;
  intensity: number;
  lineCount: number;
}> = ({ accent, intensity, lineCount }) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {new Array(lineCount).fill(true).map((_, index) => {
        const pulse = Math.max(0, Math.sin(frame * 0.06 + index * 0.85));
        const opacity = (0.025 + pulse * 0.07) * intensity;
        const width = 18 + ((index * 37) % 56);
        const top = 140 + index * 42;
        const left = index % 2 === 0 ? 0 : 1920 - width;

        return (
          <div
            key={index}
            style={{
              position: "absolute",
              top,
              left,
              width,
              height: 1,
              background: accent,
              boxShadow: `0 0 16px ${accent}`,
              opacity,
            }}
          />
        );
      })}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "repeating-linear-gradient(180deg, rgba(255,255,255,0.028) 0px, rgba(255,255,255,0.028) 1px, transparent 2px, transparent 6px)",
          opacity: 0.12 * intensity,
        }}
      />
    </AbsoluteFill>
  );
};

const TitleCard: React.FC<{
  text: string;
  accent: string;
  intensity: number;
  titleFontSize: number;
  titleWidth: number;
  signalLineCount: number;
  backgroundSrc?: string;
  backgroundTrimBeforeSeconds?: number;
  backgroundTrimAfterSeconds?: number;
  variant?: "plate" | "overlay";
}> = ({
  text,
  accent,
  intensity,
  titleFontSize,
  titleWidth,
  signalLineCount,
  backgroundSrc,
  backgroundTrimBeforeSeconds,
  backgroundTrimAfterSeconds,
  variant = "plate",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const container = spring({
    fps,
    frame,
    config: { damping: 22, stiffness: 80 },
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Split by newlines first (each line rendered in its own block),
  // then word-stagger inside each line. This preserves intentional
  // \n separators (e.g. "TITLE 1\nTITLE 2") that the old whitespace
  // regex was collapsing into a single space.
  const lines = text.split(/\r?\n/);
  const staggerFrames = 3;
  const wordFadeFrames = 14;

  const lineGrow = interpolate(frame, [0, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lineExit = exit;
  const flareOpacity =
    0.22 + Math.max(0, Math.sin(frame * 0.09)) * 0.18 * intensity;

  const bgScale = interpolate(frame, [0, durationInFrames], [1.04, 1.1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const bgTrimBefore =
    backgroundTrimBeforeSeconds !== undefined
      ? Math.round(backgroundTrimBeforeSeconds * fps)
      : undefined;
  const bgTrimAfter =
    backgroundTrimAfterSeconds !== undefined
      ? Math.round(backgroundTrimAfterSeconds * fps)
      : undefined;

  const plateBg =
    variant === "overlay"
      ? "transparent"
      : "radial-gradient(ellipse at 50% 50%, rgba(8,14,22,0.78) 0%, rgba(2,4,8,0.92) 58%, rgba(0,0,0,1) 100%)";

  return (
    <AbsoluteFill
      style={{
        background: "#000",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {backgroundSrc ? (
        <>
          <AbsoluteFill style={{ transform: `scale(${bgScale})`, opacity: 0.62 }}>
            <OffthreadVideo
              muted
              src={resolveAsset(backgroundSrc)}
              trimBefore={bgTrimBefore}
              trimAfter={bgTrimAfter}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                filter: "contrast(1.08) saturate(0.55) brightness(0.55) blur(4px)",
              }}
            />
          </AbsoluteFill>
          <AbsoluteFill
            style={{
              background:
                "linear-gradient(180deg, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.35) 40%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0.78) 100%)",
            }}
          />
        </>
      ) : null}

      <AbsoluteFill
        style={{
          background: plateBg,
        }}
      />

      <SignalTexture
        accent={accent}
        intensity={intensity * 0.7}
        lineCount={signalLineCount}
      />

      {/* Top accent line — grows from center outwards */}
      <div
        style={{
          position: "absolute",
          width: 1100 * lineGrow,
          height: 1,
          background: accent,
          boxShadow: `0 0 24px ${accent}`,
          opacity: flareOpacity * lineExit,
          transform: "translateY(-118px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1100 * lineGrow,
          height: 1,
          background: accent,
          boxShadow: `0 0 24px ${accent}`,
          opacity: flareOpacity * 0.75 * lineExit,
          transform: "translateY(118px)",
        }}
      />

      {/* Word-stagger text reveal */}
      <div
        style={{
          opacity: exit,
          width: titleWidth,
          textAlign: "center",
          fontFamily,
          fontWeight: 500,
          fontSize: titleFontSize,
          lineHeight: 1.12,
          letterSpacing: "0.16em",
          color: "#f6f4ee",
          textTransform: "uppercase",
          textShadow: "0 0 34px rgba(255,255,255,0.10), 0 0 2px rgba(0,0,0,0.8)",
        }}
      >
        {(() => {
          let wordCounter = 0;
          return lines.map((line, lineIdx) => {
            const tokens = line.split(/(\s+)/).filter((w) => w.length > 0);
            return (
              <div key={lineIdx} style={{ display: "block" }}>
                {tokens.map((w, ti) => {
                  if (/^\s+$/.test(w)) {
                    return <span key={ti}>&nbsp;</span>;
                  }
                  const startFrame = wordCounter * staggerFrames;
                  wordCounter += 1;
                  const wordOpacity = interpolate(
                    frame,
                    [startFrame, startFrame + wordFadeFrames],
                    [0, 1],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  );
                  const blur = interpolate(
                    frame,
                    [startFrame, startFrame + wordFadeFrames],
                    [6, 0],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  );
                  const ty = interpolate(
                    frame,
                    [startFrame, startFrame + wordFadeFrames],
                    [14, 0],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  );
                  return (
                    <span
                      key={ti}
                      style={{
                        display: "inline-block",
                        opacity: wordOpacity,
                        filter: `blur(${blur}px)`,
                        transform: `translateY(${ty}px)`,
                      }}
                    >
                      {w}
                    </span>
                  );
                })}
              </div>
            );
          });
        })()}
      </div>

      {/* Subtle accent dot centered under text */}
      <div
        style={{
          position: "absolute",
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: accent,
          boxShadow: `0 0 18px ${accent}`,
          opacity: 0.55 * container * lineExit,
          transform: "translateY(172px)",
        }}
      />
    </AbsoluteFill>
  );
};

const Soundtrack: React.FC<{
  src: string;
  volume: number;
  loop?: boolean;
  trimBeforeSeconds?: number;
  trimAfterSeconds?: number;
  fadeInSeconds: number;
  fadeOutSeconds: number;
}> = ({
  src,
  volume,
  loop = false,
  trimBeforeSeconds,
  trimAfterSeconds,
  fadeInSeconds,
  fadeOutSeconds,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();

  const fadeInFrames = Math.max(1, Math.round(fadeInSeconds * fps));
  const fadeOutFrames = Math.max(1, Math.round(fadeOutSeconds * fps));
  const trimBefore =
    trimBeforeSeconds !== undefined
      ? Math.round(trimBeforeSeconds * fps)
      : undefined;
  const trimAfter =
    trimAfterSeconds !== undefined
      ? Math.round(trimAfterSeconds * fps)
      : undefined;

  const fadeIn =
    fadeInSeconds <= 0
      ? volume
      : interpolate(frame, [0, fadeInFrames], [0, volume], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const fadeOut =
    fadeOutSeconds <= 0
      ? volume
      : interpolate(
          frame,
          [durationInFrames - fadeOutFrames, durationInFrames],
          [volume, 0],
          {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
          },
        );

  return (
    <Audio
      src={resolveAsset(src)}
      trimBefore={trimBefore}
      trimAfter={trimAfter}
      loop={loop}
      volume={() => Math.min(fadeIn, fadeOut)}
    />
  );
};

export const calculateCinematicMetadata: CalculateMetadataFunction<CinematicRendererProps> =
  async ({ props }) => {
    const sceneEnd =
      props.scenes.length === 0
        ? 0
        : Math.max(
            ...props.scenes.map((scene) => scene.startSeconds + scene.durationSeconds),
          );
    const endTagEnd = props.endTag
      ? props.endTag.startSeconds + props.endTag.durationSeconds
      : 0;
    const soundtrackEnd = props.soundtracks?.length
      ? Math.max(
          ...props.soundtracks.map(
            (track) => track.startSeconds + track.durationSeconds,
          ),
        )
      : 0;
    const totalSeconds = Math.max(30, sceneEnd, endTagEnd, soundtrackEnd);

    return {
      durationInFrames: Math.max(1, Math.ceil(totalSeconds * FPS)),
      fps: FPS,
      width: 1920,
      height: 1080,
    };
  };

const EditorialLabel: React.FC<{ text: string; durationSeconds?: number }> = ({
  text,
  durationSeconds = 3,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const visibleFrames = Math.min(
    durationInFrames,
    Math.max(18, Math.round(durationSeconds * fps)),
  );
  const enter = interpolate(frame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exit = interpolate(
    frame,
    [Math.max(12, visibleFrames - 12), visibleFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = frame >= visibleFrames ? 0 : Math.min(enter, exit);

  return (
    <div
      style={{
        position: "absolute",
        left: 54,
        top: 48,
        maxWidth: 720,
        display: "flex",
        alignItems: "center",
        gap: 14,
        color: "#f4f1ea",
        fontFamily: "Arial, Helvetica, sans-serif",
        fontSize: 25,
        fontWeight: 700,
        letterSpacing: 0.8,
        lineHeight: 1.2,
        opacity,
        transform: `translateY(${(1 - enter) * -8}px)`,
        textShadow: "0 2px 3px rgba(0,0,0,0.95), 0 0 10px rgba(0,0,0,0.75)",
      }}
    >
      <span
        style={{
          width: 38,
          height: 3,
          flex: "0 0 auto",
          backgroundColor: "#c9a66b",
          boxShadow: "0 1px 3px rgba(0,0,0,0.8)",
        }}
      />
      <span>{text}</span>
    </div>
  );
};

const CreditsOverlay: React.FC<{ heading?: string; lines: string[] }> = ({
  heading = "SOURCES & CREDITS",
  lines,
}) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "flex-end",
        paddingRight: 82,
        paddingBottom: 205,
        background:
          "linear-gradient(90deg, transparent 0%, rgba(0,0,0,0.08) 42%, rgba(0,0,0,0.72) 100%)",
        opacity: enter,
        pointerEvents: "none",
      }}
    >
      <div style={{ width: 650, color: "#f4f1ea", textAlign: "right" }}>
        <div
          style={{
            color: "#c9a66b",
            fontFamily,
            fontSize: 23,
            fontWeight: 700,
            letterSpacing: 2.4,
            marginBottom: 18,
          }}
        >
          {heading}
        </div>
        {lines.map((line) => (
          <div
            key={line}
            style={{
              fontFamily,
              fontSize: 22,
              fontWeight: 500,
              lineHeight: 1.45,
              marginTop: 7,
              textShadow: "0 2px 4px rgba(0,0,0,0.95)",
            }}
          >
            {line}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const CinematicRenderer: React.FC<CinematicRendererProps> = ({
  scenes,
  titleFontSize = 78,
  titleWidth = 1320,
  signalLineCount = 18,
  soundtrack,
  soundtracks,
  music,
  captions,
  subtitles,
  archiveLook,
  credits,
  endTag,
}) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {/* Layer 1: Narration audio */}
      {soundtrack ? (
        <Soundtrack
          src={soundtrack.src}
          volume={soundtrack.volume ?? 1}
          trimBeforeSeconds={soundtrack.trimBeforeSeconds}
          trimAfterSeconds={soundtrack.trimAfterSeconds}
          fadeInSeconds={soundtrack.fadeInSeconds ?? 0.3}
          fadeOutSeconds={soundtrack.fadeOutSeconds ?? 0.5}
        />
      ) : null}
      {soundtracks?.map((track, index) => (
        <Sequence
          key={`soundtrack-${index}`}
          from={Math.round(track.startSeconds * FPS)}
          durationInFrames={Math.round(track.durationSeconds * FPS)}
          premountFor={FPS}
        >
          <Soundtrack
            src={track.src}
            volume={track.volume ?? 1}
            trimBeforeSeconds={track.trimBeforeSeconds}
            trimAfterSeconds={track.trimAfterSeconds}
            fadeInSeconds={track.fadeInSeconds ?? 0}
            fadeOutSeconds={track.fadeOutSeconds ?? 0}
          />
        </Sequence>
      ))}
      {/* Layer 2: Music bed (separate track, ducked) */}
      {music ? (
        <Soundtrack
          src={music.src}
          volume={music.volume ?? 0.15}
          trimBeforeSeconds={music.trimBeforeSeconds}
          trimAfterSeconds={music.trimAfterSeconds}
          fadeInSeconds={music.fadeInSeconds ?? 2}
          fadeOutSeconds={music.fadeOutSeconds ?? 3}
          loop={music.loop ?? true}
        />
      ) : null}
      {/* Layer 3: Video scenes */}
      {scenes.map((scene) => (
        <Sequence
          key={scene.id}
          from={Math.round(scene.startSeconds * FPS)}
          durationInFrames={Math.round(scene.durationSeconds * FPS)}
          premountFor={FPS}
        >
          {scene.kind === "video" ? (
            <SceneVideo scene={scene} archiveLook={archiveLook} />
          ) : scene.kind === "image" ? (
            <SceneImage scene={scene} archiveLook={archiveLook} />
          ) : (
            <TitleCard
              text={scene.text}
              accent={scene.accent ?? "#86d8ff"}
              intensity={scene.intensity ?? 1}
              titleFontSize={titleFontSize}
              titleWidth={titleWidth}
              signalLineCount={signalLineCount}
              backgroundSrc={scene.backgroundSrc}
              backgroundTrimBeforeSeconds={scene.backgroundTrimBeforeSeconds}
              backgroundTrimAfterSeconds={scene.backgroundTrimAfterSeconds}
              variant={scene.variant}
            />
          )}
          {scene.kind !== "title" && scene.editorialLabel ? (
            <EditorialLabel
              text={scene.editorialLabel}
              durationSeconds={scene.labelDurationSeconds}
            />
          ) : null}
        </Sequence>
      ))}
      {/* Layer 4: TikTok-style captions */}
      {captions?.words ? (
        <CaptionOverlay
          words={captions.words}
          wordsPerPage={captions.wordsPerPage ?? 5}
          fontSize={captions.fontSize ?? 48}
          color={captions.color ?? "#F8FAFC"}
          highlightColor={captions.highlightColor ?? "#FBBF24"}
          backgroundColor={captions.backgroundColor ?? "rgba(0, 0, 0, 0.6)"}
        />
      ) : null}
      {endTag ? (
        <Sequence
          from={Math.round(endTag.startSeconds * FPS)}
          durationInFrames={Math.round(endTag.durationSeconds * FPS)}
          premountFor={FPS}
        >
          <EndTag
            text={endTag.text}
            palette={endTag.palette}
            fadeInSeconds={endTag.fadeInSeconds ?? 0.8}
            holdSeconds={
              endTag.holdSeconds ??
              Math.max(
                0,
                endTag.durationSeconds -
                  (endTag.fadeInSeconds ?? 0.8) -
                  (endTag.fadeOutSeconds ?? 1.2),
              )
            }
            fadeOutSeconds={endTag.fadeOutSeconds ?? 1.2}
            fontSize={endTag.fontSize ?? 64}
            overlayScrimOpacity={endTag.overlayScrimOpacity ?? 0.32}
            overlay
          />
        </Sequence>
      ) : null}
      {/* Final text layer: subtitles stay fully legible above the end-tag scrim. */}
      {subtitles?.cues?.length ? <SubtitleOverlay {...subtitles} /> : null}
      {credits?.lines?.length ? (
        <Sequence from={Math.round(credits.startSeconds * FPS)} premountFor={FPS}>
          <CreditsOverlay heading={credits.heading} lines={credits.lines} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};
