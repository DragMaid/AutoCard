/**
 * Arrows, impact effects and the card preview panel.
 *
 * The arrow is a port of `gui/screen/arrow.py`: a dashed quadratic Bezier bowed
 * perpendicular to the line, with a solid arrowhead at the tip.
 */

import { cardPreviewUrl } from "../game/assets";
import type { VisualEffect } from "../game/animations";
import type { DragArrow } from "../game/inputManager";
import { LAYOUT } from "../game/layout";
import type { AttackArrow } from "../game/renderEngine";
import type { Card } from "../types/game";
import { CardFace } from "./CardFace";
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
  length = 15,
  width = 7,
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
        color: "rgb(0, 255, 0)",
      },
    });
  }

  return (
    <svg
      className="pointer-events-none absolute inset-0"
      width={LAYOUT.grid.width + LAYOUT.grid.originX * 2}
      height="100%"
      style={{ width: "100%", height: "100%", overflow: "visible" }}
    >
      {arrows.map(({ arrow, key }) => (
        <g key={key}>
          {curveSegments(arrow.from, arrow.to).map((d, index) => (
            <path
              key={index}
              d={d}
              stroke={arrow.color}
              strokeWidth={5}
              strokeLinecap="round"
              fill="none"
            />
          ))}
          <polygon
            points={arrowHead(arrow.to, arrow.from)}
            fill={arrow.color}
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
 * The large card preview, ported from `gui/background/preview_card_table.py`.
 *
 * Shows the empty plate until a card is selected, then renders that card at
 * panel size — which is where a card's description is actually legible.
 *
 * @param props - The card to display, or null.
 * @returns The preview panel.
 */
export function CardPreview({ card }: CardPreviewProps) {
  const rect = LAYOUT.areas.previewTable;

  return (
    <div className="pointer-events-none absolute" style={rectStyle(rect)}>
      {card ? (
        <CardFace
          card={card}
          width={rect.width}
          height={rect.height}
          faceDown={false}
        />
      ) : (
        <img
          src={cardPreviewUrl()}
          alt=""
          draggable={false}
          className="h-full w-full"
          style={{ objectFit: "fill" }}
        />
      )}
    </div>
  );
}
