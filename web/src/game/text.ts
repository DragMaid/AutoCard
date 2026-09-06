/**
 * Text measurement and fitting, reproducing `gui/cards/card_gui.py`.
 *
 * The pygame card face shrinks the name font until it fits the card width, and
 * shrinks the description font until the wrapped lines fit the text box. Both
 * loops are ported here on top of a cached canvas context so a card face can be
 * laid out without touching the DOM.
 */

/** Font stack standing in for pygame's `SysFont(None, size)`. */
export const CARD_FONT_FAMILY =
  'system-ui, -apple-system, "Segoe UI", "DejaVu Sans", "Liberation Sans", sans-serif';

let context: CanvasRenderingContext2D | null = null;

/** Returns a shared 2D context used purely for text measurement. */
function measureContext(): CanvasRenderingContext2D | null {
  if (context) return context;
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  context = canvas.getContext("2d");
  return context;
}

const widthCache = new Map<string, number>();

/**
 * Measures the rendered width of a string.
 *
 * @param text - The string to measure.
 * @param fontSize - Font size in stage pixels.
 * @param weight - CSS font weight.
 * @returns Width in stage pixels; a rough estimate when canvas is unavailable.
 */
export function measureText(
  text: string,
  fontSize: number,
  weight = "400",
): number {
  const key = `${weight}|${fontSize}|${text}`;
  const cached = widthCache.get(key);
  if (cached !== undefined) return cached;

  const ctx = measureContext();
  let width: number;
  if (ctx) {
    ctx.font = `${weight} ${fontSize}px ${CARD_FONT_FAMILY}`;
    width = ctx.measureText(text).width;
  } else {
    width = text.length * fontSize * 0.5;
  }

  widthCache.set(key, width);
  return width;
}

/**
 * Wraps text to a pixel width, breaking on spaces and honouring newlines.
 *
 * Mirrors `CardGUI._render_wrapped_text`'s inner `wrap_text_for_font`: a word
 * that cannot fit on its own is placed on a line by itself rather than split.
 *
 * @param text - Text to wrap, may contain newlines.
 * @param maxWidth - Available width in stage pixels.
 * @param fontSize - Font size in stage pixels.
 * @returns The wrapped lines.
 */
export function wrapText(
  text: string,
  maxWidth: number,
  fontSize: number,
): string[] {
  const lines: string[] = [];

  for (const paragraph of text.split("\n")) {
    const words = paragraph.split(" ");
    let current: string[] = [];

    for (const word of words) {
      const candidate = [...current, word];
      if (measureText(candidate.join(" "), fontSize) > maxWidth) {
        if (current.length) {
          lines.push(current.join(" "));
          current = [word];
        } else {
          lines.push(word);
          current = [];
        }
      } else {
        current = candidate;
      }
    }

    if (current.length) lines.push(current.join(" "));
  }

  return lines;
}

/** A description laid out to fit its box. */
export interface FittedText {
  lines: string[];
  fontSize: number;
  lineHeight: number;
}

/**
 * Shrinks a font until the wrapped text fits the given box.
 *
 * Mirrors the `while True` loop in `CardGUI._render_wrapped_text`, including its
 * floor of 6px and its truncation to the number of lines that fit.
 *
 * @param text - Text to lay out.
 * @param boxWidth - Available width in stage pixels.
 * @param boxHeight - Available height in stage pixels.
 * @param startSize - Starting font size.
 * @param minSize - Smallest font size to try.
 * @returns The chosen font size and the lines that fit.
 */
export function fitParagraph(
  text: string,
  boxWidth: number,
  boxHeight: number,
  startSize: number,
  minSize = 6,
): FittedText {
  let fontSize = Math.max(minSize, startSize);

  for (;;) {
    const lineHeight = fontSize * 1.15;
    const lines = wrapText(text, boxWidth, fontSize);
    const maxLines = Math.max(1, Math.floor(boxHeight / lineHeight));

    if (lines.length <= maxLines || fontSize <= minSize) {
      return { lines: lines.slice(0, maxLines), fontSize, lineHeight };
    }
    fontSize -= 1;
  }
}

/**
 * Shrinks a single line until it fits a width.
 *
 * Mirrors the name-shrinking loop in `CardGUI._render_card_with_text`.
 *
 * @param text - The line to fit.
 * @param maxWidth - Available width in stage pixels.
 * @param startSize - Starting font size.
 * @param minSize - Smallest font size to try.
 * @returns The largest font size at which the line fits.
 */
export function fitLine(
  text: string,
  maxWidth: number,
  startSize: number,
  minSize = 6,
): number {
  let fontSize = Math.max(minSize, startSize);
  while (measureText(text, fontSize, "700") > maxWidth && fontSize > minSize) {
    fontSize -= 1;
  }
  return fontSize;
}

/**
 * Builds the description block shown on a card face.
 *
 * Monsters get the type/level preamble that `CardGUI` adds; everything else
 * gets the plain description line.
 *
 * @param card - The card being rendered.
 * @returns The multi-line description string.
 */
export function describeCard(card: {
  description?: string;
  star?: number;
  monster_type?: string;
}): string {
  const description = card.description ?? "";
  if (card.star && card.monster_type) {
    return [
      `Type: ${card.monster_type}`,
      `Level: ${card.star}*`,
      `Description: ${description}`,
    ].join("\n");
  }
  return `Description: ${description}`;
}
