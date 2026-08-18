import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CinematicImageScene } from "../cinematic/types";
import { ArchiveFilmLook, archiveFilmFilter, gateWeaveOffset } from "./ArchiveFilmLook";
import { CinematicArchiveLookConfig } from "../cinematic/types";

function resolveAsset(src: string): string {
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:")
  ) {
    return src;
  }
  const clean = src.replace(/^file:\/\/?/, "");
  if (clean.startsWith("/") || /^[A-Za-z]:[/\\]/.test(clean)) {
    const posix = clean.replace(/\\/g, "/");
    return posix.startsWith("/") ? `file://${posix}` : `file:///${posix}`;
  }
  return staticFile(clean);
}

/**
 * Still image with a slow Ken Burns move.
 *
 * Why this exists: a lot of this documentary has no filmable subject. There
 * is no stock video of "documented descent through a cadet branch", and for
 * pre-1918 material photographs often exist where film does not. A held
 * still is dead on screen; a slow, continuous move keeps it alive without
 * pretending to be motion footage.
 *
 * Movement rules, learned the hard way:
 *  - One move per image. A zoom AND a pan in different directions reads as
 *    drift, not intent.
 *  - Slow. Default is a 6% scale change across the whole scene; anything
 *    faster looks like a slideshow effect.
 *  - Always start above 1.0 scale. At exactly 1.0 a pan exposes the edge of
 *    the image.
 */
export const SceneImage: React.FC<{
  scene: CinematicImageScene;
  archiveLook?: CinematicArchiveLookConfig;
}> = ({ scene, archiveLook }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const fadeInFrames = scene.fadeInFrames ?? 10;
  const fadeOutFrames = scene.fadeOutFrames ?? 10;
  const fadeOutStart = Math.max(fadeInFrames, durationInFrames - fadeOutFrames);
  const fadeIn =
    fadeInFrames === 0
      ? 1
      : interpolate(frame, [0, fadeInFrames], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const fadeOut =
    fadeOutFrames === 0
      ? 1
      : interpolate(frame, [fadeOutStart, durationInFrames], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const opacity = Math.min(fadeIn, fadeOut);

  const move = scene.move ?? "zoom-in";
  const amount = scene.moveAmount ?? 0.06;
  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Base scale is always > 1 so a pan never reveals the image edge.
  const base = 1.04;
  let scale = base;
  let translateX = 0;
  let translateY = 0;

  switch (move) {
    case "zoom-in":
      scale = base + amount * progress;
      break;
    case "zoom-out":
      scale = base + amount * (1 - progress);
      break;
    case "pan-left":
      scale = base + amount;
      translateX = -amount * 100 * progress * 0.5;
      break;
    case "pan-right":
      scale = base + amount;
      translateX = amount * 100 * progress * 0.5;
      break;
    case "pan-up":
      scale = base + amount;
      translateY = -amount * 100 * progress * 0.5;
      break;
    case "pan-down":
      scale = base + amount;
      translateY = amount * 100 * progress * 0.5;
      break;
    case "still":
    default:
      scale = base;
      break;
  }

  const archiveIntensity = scene.archiveIntensity ?? archiveLook?.intensity ?? 0;
  const archiveOn = archiveIntensity > 0;
  const weave =
    archiveOn && archiveLook?.gateWeave !== false
      ? gateWeaveOffset(frame, archiveIntensity)
      : 0;

  const filter =
    scene.filter ??
    (archiveOn && archiveLook?.colorGrade !== false
      ? archiveFilmFilter(archiveIntensity)
      : "contrast(1.04) saturate(0.9) brightness(0.94)");

  return (
    <AbsoluteFill style={{ backgroundColor: "#020407", opacity }}>
      <Img
        src={resolveAsset(scene.src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform:
            "scale(" +
            scale +
            ") translate(" +
            translateX +
            "%, " +
            (translateY + weave / 10) +
            "%)",
          filter,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.52) 100%)",
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
