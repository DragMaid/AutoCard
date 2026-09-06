/**
 * Card artwork, ported from `CardGUI._render_card_with_text`.
 *
 * The pygame face composites four things onto the scaled art: a description box
 * near the bottom, the card name just above it, and (for monsters, via
 * `CardStatOverlay`) an ATK/DEF/star line outside the card. Every measurement
 * below is the same fraction of the 64x81 base card the Python code uses, so the
 * face scales identically at hand size and at preview size.
 */

import { memo, useMemo } from "react";

import { cardBackUrl, resolveCardImage } from "../game/assets";
import { CARD_FONT_FAMILY, describeCard, fitLine, fitParagraph } from "../game/text";
import type { Card } from "../types/game";

/** Base card size from `CardGUI.BASE_SIZE`. */
const BASE_WIDTH = 64;
const BASE_HEIGHT = 81;
const TEXT_PADDING = 4;

export interface CardFaceProps {
  card: Card;
  width: number;
  height: number;
  /** Renders the card back instead of its face. */
  faceDown: boolean;
  /** Draws the card upside down, matching `CardGUI.flip` for opponent cards. */
  flipped?: boolean;
  /** Hides the name/description overlay, e.g. for tiny hand cards. */
  showText?: boolean;
}

/**
 * Renders a single card face at an arbitrary size.
 *
 * @param props - Card, target size and presentation flags.
 * @returns The composed card face.
 */
function CardFaceImpl({
  card,
  width,
  height,
  faceDown,
  flipped = false,
  showText = true,
}: CardFaceProps) {
  const layout = useMemo(() => {
    const scaleY = height / BASE_HEIGHT;

    const boxWidth = (width * 62) / BASE_WIDTH;
    const boxHeight = (height * 17) / BASE_HEIGHT;
    const boxBottomOffset = (height * 4) / BASE_HEIGHT;
    const boxX = (width - boxWidth) / 2;
    const boxY = height - boxHeight - boxBottomOffset;

    const innerWidth = boxWidth - 2 * TEXT_PADDING;
    const innerHeight = boxHeight - 2 * TEXT_PADDING;

    const description = fitParagraph(
      describeCard(card as unknown as Record<string, never>),
      innerWidth,
      innerHeight,
      Math.max(6, Math.round(12 * scaleY)),
    );

    const nameSize = fitLine(
      card.name,
      width - 2 * TEXT_PADDING,
      Math.max(6, Math.round(14 * scaleY)),
    );

    return {
      boxX,
      boxY,
      boxWidth,
      boxHeight,
      innerWidth,
      innerHeight,
      description,
      nameSize,
    };
  }, [card, width, height]);

  const imageUrl = faceDown ? cardBackUrl() : resolveCardImage(card.image_path);

  return (
    <div
      className="relative select-none overflow-hidden"
      style={{
        width,
        height,
        transform: flipped ? "scaleY(-1)" : undefined,
      }}
    >
      <img
        src={imageUrl}
        alt=""
        draggable={false}
        className="absolute inset-0 block h-full w-full"
        style={{ objectFit: "fill", imageRendering: "auto" }}
      />

      {!faceDown && showText && (
        <>
          {/* Name, sitting directly above the description box. */}
          <div
            className="absolute text-center font-bold leading-none text-white"
            style={{
              left: 0,
              width,
              bottom: height - layout.boxY + TEXT_PADDING,
              fontFamily: CARD_FONT_FAMILY,
              fontSize: layout.nameSize,
              textShadow: "1px 1px 0 rgba(0,0,0,0.95)",
              whiteSpace: "nowrap",
            }}
          >
            {card.name}
          </div>

          {/* Description box. */}
          <div
            className="absolute overflow-hidden"
            style={{
              left: layout.boxX + TEXT_PADDING,
              top: layout.boxY + TEXT_PADDING,
              width: layout.innerWidth,
              height: layout.innerHeight,
              fontFamily: CARD_FONT_FAMILY,
              fontSize: layout.description.fontSize,
              lineHeight: `${layout.description.lineHeight}px`,
              color: "rgb(0,0,0)",
            }}
          >
            {layout.description.lines.map((line, index) => (
              <div key={index} className="whitespace-nowrap">
                {line}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export const CardFace = memo(CardFaceImpl);

export interface StatOverlayProps {
  card: Card;
  /** Placed above the card for the local player, below for the opponent. */
  position: "above" | "below";
}

/**
 * ATK/DEF/star line drawn outside a monster card.
 *
 * Ported from `CardStatOverlay.draw`, including its fixed 20px font and its
 * black outline. Note the inversion in the original: the overlay configured as
 * `"bottom"` (the local player) is drawn *above* the card.
 *
 * @param props - The monster card and which side to draw on.
 * @returns The stat line, or null when the card is not a monster.
 */
export function StatOverlay({ card, position }: StatOverlayProps) {
  if (card.card_type !== "MONSTER") return null;

  const text = `${card.attack}/${card.defend}/${card.star}*`;
  const outline = [
    "-1px 0 0 #000",
    "1px 0 0 #000",
    "0 -1px 0 #000",
    "0 1px 0 #000",
  ].join(", ");

  return (
    <div
      className="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap font-bold leading-none text-white"
      style={{
        fontFamily: CARD_FONT_FAMILY,
        fontSize: 20,
        textShadow: outline,
        ...(position === "above" ? { bottom: "100%" } : { top: "100%" }),
      }}
    >
      {text}
    </div>
  );
}
