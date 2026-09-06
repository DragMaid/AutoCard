/**
 * Arrows, impact effects and the card inspector.
 *
 * The arrow is a port of `gui/screen/arrow.py`: a dashed quadratic Bezier bowed
 * perpendicular to the line, with a solid arrowhead at the tip.
 */

import { cardPreviewUrl } from "../game/assets";
import type { VisualEffect } from "../game/animations";
import type { DragArrow } from "../game/inputManager";
import { LAYOUT } from "../game/layout";
import type { AttackArrow } from "../game/renderEngine";
import { COLORS, PIXEL_FONT, pixelPanel } from "../game/theme";
import type { Card } from "../types/game";
import { CardDetail } from "./CardFace";
import { rectStyle } from "./Board";

/** Height of the Bezier bow, matching `draw_stripe_curve`'s default. */
const CURVE_HEIGHT = 80;

/** Builds the dashed segments of a bowed arrow. */
function curveSegments(
  from: { x: number; y: number },
  to: { x: number; y: number },
): string[] {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (length === 0) return [];

  // Control point offset perpendicular to the line.
  const cx = (from.x + to.x) / 2 + (-dy / length) * CURVE_HEIGHT;
  const cy = (from.y + to.y) / 2 + (dx / length) * CURVE_HEIGHT;

  const steps = 60;
  const points: [number, number][] = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const inv = 1 - t;
    points.push([
      inv * inv * from.x + 2 * inv * t * cx + t * t * to.x,
      inv * inv * from.y + 2 * inv * t * cy + t * t * to.y,
    ]);
  }

  // Every other segment is a gap, as the pygame version does with dash_skip=2.
  const segments: string[] = [];
  for (let i = 0; i < points.length - 1; i += 2) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[i + 1];
    segments.push(`M ${x1} ${y1} L ${x2} ${y2}`);
  }
  return segments;
}

/** Builds the arrowhead polygon points. */
function arrowHead(
  tip: { x: number; y: number },
  tail: { x: number; y: number },
  length = 18,
  width = 9,
): string {
  const angle = Math.atan2(tip.y - tail.y, tip.x - tail.x);
  const lx = tip.x - length * Math.cos(angle) + width * Math.sin(angle);
  const ly = tip.y - length * Math.sin(angle) - width * Math.cos(angle);
  const rx = tip.x - length * Math.cos(angle) - width * Math.sin(angle);
  const ry = tip.y - length * Math.sin(angle) + width * Math.cos(angle);
  return `${tip.x},${tip.y} ${lx},${ly} ${rx},${ry}`;
}

export interface ArrowLayerProps {
  dragArrow: DragArrow | null;
  attackIndicators: AttackArrow[];
  effects: VisualEffect[];
}

/**
 * Draws the drag arrow, queued-attack arrows and impact bursts.
 *
 * @param props - Current arrows and effects.
 * @returns An SVG overlay covering the stage.
 */
export function ArrowLayer({
  dragArrow,
  attackIndicators,
  effects,
}: ArrowLayerProps) {
  const arrows: Array<{ arrow: AttackArrow; key: string }> = attackIndicators.map(
    (arrow, index) => ({ arrow, key: `queued-${index}` }),
  );

  if (dragArrow) {
    arrows.push({
      key: "drag",
      arrow: {
        from: dragArrow.from,
        to: dragArrow.to,
        color: COLORS.positive,
      },
    });
  }

  return (
    <svg
      className="pointer-events-none absolute inset-0"
      style={{
        width: "100%",
        height: "100%",
        overflow: "visible",
        // Above every card sprite, including one being dragged.
        zIndex: 1500,
      }}
    >
      {arrows.map(({ arrow, key }) => (
        <g key={key}>
          {curveSegments(arrow.from, arrow.to).map((d, index) => (
            <path
              key={index}
              d={d}
              stroke="rgba(0, 0, 0, 0.6)"
              strokeWidth={8}
              strokeLinecap="butt"
              fill="none"
            />
          ))}
          {curveSegments(arrow.from, arrow.to).map((d, index) => (
            <path
              key={`fg-${index}`}
              d={d}
              stroke={arrow.color}
              strokeWidth={5}
              strokeLinecap="butt"
              fill="none"
            />
          ))}
          <polygon
            points={arrowHead(arrow.to, arrow.from)}
            fill={arrow.color}
            stroke="rgba(0, 0, 0, 0.6)"
            strokeWidth={2}
          />
        </g>
      ))}

      {effects.map((effect) => (
        <EffectBurst key={effect.id} effect={effect} />
      ))}
    </svg>
  );
}

/** A single expanding ring, standing in for `gui/effects`. */
function EffectBurst({ effect }: { effect: VisualEffect }) {
  const progress = Math.min(
    (performance.now() - effect.born) / effect.duration,
    1,
  );

  const palette: Record<VisualEffect["kind"], string> = {
    slam: "rgb(255, 236, 158)",
    merge: "rgb(147, 197, 253)",
    "trap-glow": "rgb(248, 113, 113)",
    "trap-pulse": "rgb(251, 191, 36)",
    "spell-glow": "rgb(196, 132, 252)",
    "hit-player": "rgb(248, 113, 113)",
  };

  return (
    <circle
      cx={effect.x}
      cy={effect.y}
      r={10 + progress * 55}
      fill="none"
      stroke={palette[effect.kind]}
      strokeWidth={4 * (1 - progress)}
      opacity={1 - progress}
    />
  );
}

export interface CardPreviewProps {
  card: Card | null;
}

/**
 * The card inspector.
 *
 * This is the one place a card is big enough for its description to be a
 * sentence rather than a smear, so the board cards no longer try to carry it.
 *
 * @param props - The card to display, or null.
 * @returns The inspector panel.
 */
export function CardPreview({ card }: CardPreviewProps) {
  const rect = LAYOUT.areas.previewTable;
  const padding = 12;

  return (
    <div
      className="pointer-events-none absolute"
      style={{ ...rectStyle(rect), ...pixelPanel() }}
    >
      <div
        className="absolute left-0 right-0 flex justify-center"
        style={{ top: 6 }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 8,
            letterSpacing: "0.2em",
            color: COLORS.textFaint,
          }}
        >
          {card ? "CARD" : "NO CARD SELECTED"}
        </span>
      </div>

      <div
        className="absolute"
        style={{
          left: padding,
          top: 22,
          width: rect.width - 2 * padding,
          height: rect.height - 22 - padding,
        }}
      >
        {card ? (
          <CardDetail
            card={card}
            width={rect.width - 2 * padding}
            height={rect.height - 22 - padding}
          />
        ) : (
          <EmptyPlate height={rect.height - 22 - padding} />
        )}
      </div>
    </div>
  );
}

/** Native aspect of `card-preview.png`, which is narrower than a card. */
const PLATE_ASPECT = 16 / 25;

/** The empty inspector: the plate art plus a hint at what fills it. */
function EmptyPlate({ height }: { height: number }) {
  const plateHeight = Math.round(height * 0.62);

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-4">
      <img
        src={cardPreviewUrl()}
        alt=""
        draggable={false}
        className="pixel-art block opacity-60"
        style={{
          height: plateHeight,
          width: Math.round(plateHeight * PLATE_ASPECT),
        }}
      />
      <span
        className="max-w-[200px] text-center leading-relaxed"
        style={{
          fontFamily: PIXEL_FONT,
          fontSize: 9,
          color: COLORS.textFaint,
        }}
      >
        Click a card to inspect it
      </span>
    </div>
  );
}
