import React from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";

/**
 * Archival-documentary treatment for stock footage.
 *
 * Modern 4K stock and 1910s newsreel cut together badly: the stock reads as
 * "today, colour-graded, drone", the archive as "damaged, grainy, grey". This
 * overlay pushes the modern material toward the archive rather than the other
 * way round, so the two can share a sequence.
 *
 * Layers, in the order the eye notices them:
 *   1. Colour grade  -- CSS filters on the video underneath (applied by the
 *      caller via archiveFilmFilter, not here).
 *   2. Grain         -- animated fractal noise, the single most effective cue.
 *   3. Vignette      -- period lenses fell off hard at the corners.
 *   4. Gate weave    -- sub-pixel vertical drift, as film moved in the gate.
 *   5. Dust/hairs    -- sparse, brief specks. Deliberately rare.
 *   6. Flicker       -- small exposure instability between frames.
 *
 * Every layer is off at intensity = 0 and tuned to be *restrained* at 1.
 * Overcooked film effects read as a filter, not as age -- the goal is that a
 * viewer never consciously notices it.
 */
export interface ArchiveFilmLookProps {
  /** 0 = clean, 1 = full treatment. Above ~1.2 it looks like a gimmick. */
  intensity?: number;
  /** Animated grain. */
  grain?: boolean;
  /** Corner falloff. */
  vignette?: boolean;
  /** Sparse dust specks and hairs. */
  dust?: boolean;
  /** Frame-to-frame exposure instability. */
  flicker?: boolean;
  /** Deterministic seed -- keeps renders reproducible across passes. */
  seed?: string;
}

/**
 * CSS filter chain approximating FFmpeg's vintage_film profile
 * (colorbalance + curves + desaturation), for use on the video element
 * itself. Kept beside the overlay so the two stay visually consistent.
 */
export function archiveFilmFilter(intensity = 1): string {
  const t = Math.max(0, Math.min(1.5, intensity));
  const saturate = 1 - 0.42 * t;
  const contrast = 1 + 0.1 * t;
  const brightness = 1 - 0.08 * t;
  const sepia = 0.16 * t;
  return [
    "saturate(" + saturate.toFixed(3) + ")",
    "contrast(" + contrast.toFixed(3) + ")",
    "brightness(" + brightness.toFixed(3) + ")",
    "sepia(" + sepia.toFixed(3) + ")",
  ].join(" ");
}

/** Sub-pixel vertical drift, as film weaving in the projector gate. */
export function gateWeaveOffset(frame: number, intensity = 1): number {
  return (
    (Math.sin(frame * 0.31) * 0.6 + Math.sin(frame * 0.113) * 0.4) * intensity
  );
}
const DUST_SLOTS = 7;

export const ArchiveFilmLook: React.FC<ArchiveFilmLookProps> = ({
  intensity = 1,
  grain = true,
  vignette = true,
  dust = true,
  flicker = true,
  seed = "archive",
}) => {
  const frame = useCurrentFrame();
  const t = Math.max(0, Math.min(1.5, intensity));
  if (t === 0) return null;

  // Exposure instability: small, and biased so it mostly darkens.
  const flickerOpacity = flicker
    ? (random(seed + "-flicker-" + frame) * 0.055 + 0.01) * t
    : 0;

  // Grain plate re-seeds every other frame -- per-frame is noisier than real
  // film and draws attention to itself.
  const grainSeed = Math.floor(frame / 2);
  const grainSvg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'>" +
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85'" +
    " numOctaves='3' seed='" + grainSeed + "'/>" +
    "<feColorMatrix type='saturate' values='0'/></filter>" +
    "<rect width='220' height='220' filter='url(#n)'/></svg>";

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {grain ? (
        <AbsoluteFill
          style={{
            opacity: 0.16 * t,
            mixBlendMode: "overlay",
            backgroundImage:
              'url("data:image/svg+xml;utf8,' +
              encodeURIComponent(grainSvg) +
              '")',
            backgroundRepeat: "repeat",
          }}
        />
      ) : null}

      {vignette ? (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(0,0,0,0) 44%," +
              " rgba(0,0,0,0.28) 78%, rgba(0,0,0,0.62) 100%)",
            opacity: t,
          }}
        />
      ) : null}

      {/* Uneven emulsion: a very soft warm bloom, off-centre. */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 38% 30%, rgba(255,232,190,0.05) 0%," +
            " rgba(0,0,0,0) 55%)",
          opacity: t,
        }}
      />

      {dust
        ? new Array(DUST_SLOTS).fill(true).map((_, index) => {
            // Each slot shows a speck for 2 frames every ~18-50 frames, at a
            // position that changes on every appearance.
            const cycle = 18 + index * 5;
            if (frame % cycle >= 2) return null;
            const key =
              seed + "-dust-" + index + "-" + Math.floor(frame / cycle);
            const left = random(key + "-x") * 100;
            const top = random(key + "-y") * 100;
            const isHair = random(key + "-h") > 0.72;
            const size = 1 + random(key + "-s") * 2.4;
            return (
              <div
                key={index}
                style={{
                  position: "absolute",
                  left: left + "%",
                  top: top + "%",
                  width: isHair ? size * 0.5 : size,
                  height: isHair ? size * 9 : size,
                  borderRadius: isHair ? 1 : "50%",
                  background:
                    random(key + "-p") > 0.4
                      ? "rgba(255,255,255,0.5)"
                      : "rgba(20,16,10,0.5)",
                  transform: "rotate(" + random(key + "-r") * 180 + "deg)",
                  opacity: 0.5 * t,
                }}
              />
            );
          })
        : null}

      {flickerOpacity > 0 ? (
        <AbsoluteFill style={{ background: "#000", opacity: flickerOpacity }} />
      ) : null}

      {/* Faint horizontal scan texture -- telecine transfer artefact. */}
      <AbsoluteFill
        style={{
          background:
            "repeating-linear-gradient(180deg, rgba(0,0,0,0.05) 0px," +
            " rgba(0,0,0,0.05) 1px, transparent 2px, transparent 4px)",
          opacity: 0.35 * t,
        }}
      />
    </AbsoluteFill>
  );
};

/**
 * Opening/closing exposure ramp, as a projector coming up to speed.
 * Returns a multiplier for the scene's own opacity.
 */
export function projectorRamp(
  frame: number,
  durationInFrames: number,
  rampFrames = 6,
): number {
  if (rampFrames <= 0) return 1;
  return Math.min(
    interpolate(frame, [0, rampFrames], [0.82, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
    interpolate(
      frame,
      [durationInFrames - rampFrames, durationInFrames],
      [1, 0.82],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    ),
  );
}
