/**
 * Card rendering.
 *
 * The source art is 64x81 and already reserves a light band across its lower
 * quarter for text. The pygame build filled that band with the card's whole
 * description, which at hand size meant six-pixel type nobody could read. Here
 * the band carries only what you need to scan the board — name, then ATK/DEF —
 * and the full text lives in the preview panel, at a size where it is actually
 * a sentence.
 */

import { memo, useMemo } from "react";

import { cardBackUrl, resolveCardImage } from "../game/assets";
import { CARD_ASPECT } from "../game/layout";
import { fitLine, fitParagraph } from "../game/text";
import { BODY_FONT, COLORS, PIXEL_FONT, TEXT_OUTLINE } from "../game/theme";
import type { Card } from "../types/game";

/**
 * Where the art's built-in light text band sits, as fractions of card height.
 *
 * Every card shares one 64x81 frame template, and sampling it shows the band
 * running from row 60 to row 75 — row 76 onwards is the dark border. Writing
 * past row 75 is what put the old stat line half outside the card.
 */
const BAND_TOP = 60 / 81;
const BAND_BOTTOM = 76 / 81;

/** Height of the stat strip drawn just above the band, in source rows. */
const STAT_ROWS = 13;

export interface CardFaceProps {
  card: Card;
  width: number;
  height: number;
  /** Renders the card back instead of its face. */
  faceDown: boolean;
}

/** Human-readable label for a card's kind. */
function kindLabel(card: Card): string {
  if (card.card_type === "MONSTER") return card.monster_type.replace("_", " ");
  return card.card_type;
}

/** Accent colour identifying a card's kind. */
function kindColor(card: Card): string {
  switch (card.card_type) {
    case "MONSTER":
      return COLORS.gold;
    case "SPELL":
      return "#9d7bff";
    case "TRAP":
      return COLORS.opponent;
  }
}

/**
 * Renders a single card at board size.
 *
 * @param props - Card, target size and presentation flags.
 * @returns The composed card.
 */
function CardFaceImpl({
  card,
  width,
  height,
  faceDown,
}: CardFaceProps) {
  const band = useMemo(() => {
    const top = height * BAND_TOP;
    const nameHeight = height * (BAND_BOTTOM - BAND_TOP);
    const statHeight = (height * STAT_ROWS) / 81;

    return {
      top,
      nameHeight,
      // Stats sit in their own strip above the band, over the bottom edge of
      // the artwork, so the name gets the whole light band to itself.
      statTop: top - statHeight,
      statHeight,
      // Scales with the card so the same component serves a 79px board card
      // and a 160px inspector card without a second code path.
      nameSize: fitLine(
        card.name,
        width - 6,
        Math.min(Math.round(height * 0.11), Math.round(nameHeight * 0.62)),
        5,
      ),
    };
  }, [card, width, height]);

  const imageUrl = faceDown ? cardBackUrl() : resolveCardImage(card.image_path);

  return (
    <div
      className="relative select-none overflow-hidden"
      style={{ width, height }}
    >
      <img
        src={imageUrl}
        alt=""
        draggable={false}
        className="pixel-art absolute inset-0 block h-full w-full"
      />

      {!faceDown && (
        <>
          <div
            className="absolute flex items-center justify-center overflow-hidden whitespace-nowrap px-[3px] font-bold leading-none"
            style={{
              left: 0,
              top: band.top,
              width,
              height: band.nameHeight,
              fontFamily: PIXEL_FONT,
              fontSize: band.nameSize,
              color: "#14101f",
            }}
          >
            {card.name}
          </div>

          {card.card_type === "MONSTER" && (
            <div
              className="absolute flex items-center justify-center gap-[4px] leading-none"
              style={{
                left: 0,
                top: band.statTop,
                width,
                height: band.statHeight,
                backgroundColor: "rgba(8, 6, 18, 0.86)",
                borderTop: "1px solid rgba(255, 255, 255, 0.18)",
                fontFamily: PIXEL_FONT,
                fontSize: Math.min(9, Math.round(band.statHeight * 0.62)),
              }}
            >
              <span style={{ color: "#ff8a8a" }}>{card.attack}</span>
              <span style={{ color: "#6b6799" }}>/</span>
              <span style={{ color: "#8fb0ff" }}>{card.defend}</span>
            </div>
          )}
        </>
      )}

      {/* Level, tucked into the art's own top-right corner. */}
      {!faceDown && card.card_type === "MONSTER" && (
        <div
          className="absolute px-[2px] leading-none"
          style={{
            right: 2,
            top: 2,
            fontFamily: PIXEL_FONT,
            fontSize: 8,
            color: COLORS.gold,
            backgroundColor: "rgba(8, 6, 18, 0.8)",
            textShadow: TEXT_OUTLINE,
          }}
        >
          L{card.star}
        </div>
      )}
    </div>
  );
}

export const CardFace = memo(CardFaceImpl);

export interface CardDetailProps {
  card: Card;
  /** Width available for the whole block. */
  width: number;
  /** Height available for the whole block. */
  height: number;
}

/**
 * The card inspector: art at a readable size, then the card's actual text.
 *
 * Splitting art from text is the point — the art keeps its native aspect and
 * is drawn without any overlay, while the name, type line, stats and
 * description get laid out as ordinary type underneath it.
 *
 * @param props - The card and the space it has to fill.
 * @returns The detail block.
 */
export function CardDetail({ card, width, height }: CardDetailProps) {
  // Height of the caption between the card and the description: the type line
  // and, for monsters, the stat chips.
  const captionHeight = card.card_type === "MONSTER" ? 64 : 20;

  // Give the card as much room as it can take without squeezing the caption or
  // leaving the description with under two lines.
  const artHeight = Math.min(
    height - captionHeight - 46,
    Math.round(width * 0.78),
  );
  const artWidth = Math.round(artHeight * CARD_ASPECT);

  const description = fitParagraph(
    card.description || "No effect.",
    width - 16,
    height - artHeight - captionHeight - 20,
    11,
    9,
  );

  return (
    <div
      className="flex h-full w-full flex-col items-center justify-center"
      style={{ width, height }}
    >
      {/* The full card, including its own name band — the inspector is the
          one place the art is big enough for that band to be legible. */}
      <div style={{ boxShadow: "4px 4px 0 rgba(0, 0, 0, 0.55)" }}>
        <CardFace
          card={card}
          width={artWidth}
          height={artHeight}
          faceDown={false}
        />
      </div>

      <div
        className="mt-3 w-full text-center leading-none"
        style={{
          fontFamily: PIXEL_FONT,
          fontSize: 9,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: kindColor(card),
        }}
      >
        {kindLabel(card)}
        {card.card_type === "MONSTER" && ` · LV ${card.star}`}
      </div>

      {card.card_type === "MONSTER" && (
        <div className="mt-2 flex w-full justify-center gap-2">
          <StatChip label="ATK" value={card.attack} color="#ff7a7a" />
          <StatChip label="DEF" value={card.defend} color="#7aa8ff" />
        </div>
      )}

      <div
        className="mt-3 w-full px-2 text-center"
        style={{
          fontFamily: BODY_FONT,
          fontSize: description.fontSize,
          lineHeight: `${description.lineHeight}px`,
          color: COLORS.textDim,
        }}
      >
        {description.lines.map((line, index) => (
          <div key={index}>{line}</div>
        ))}
      </div>
    </div>
  );
}

/** One labelled stat readout in the inspector. */
function StatChip({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      className="flex min-w-[76px] flex-col items-center gap-0.5 px-2 py-1"
      style={{
        backgroundColor: "rgba(6, 6, 18, 0.7)",
        border: `2px solid ${color}55`,
        fontFamily: PIXEL_FONT,
      }}
    >
      <span
        style={{ fontSize: 8, letterSpacing: "0.16em", color: COLORS.textFaint }}
      >
        {label}
      </span>
      <span style={{ fontSize: 15, color }}>{value}</span>
    </div>
  );
}
