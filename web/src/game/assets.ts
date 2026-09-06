/**
 * Asset resolution.
 *
 * Card records carry `image_path` as an absolute filesystem path built by the
 * Python factories (`Config.ASSET_DIR / texture`), for example
 * `/home/user/AutoCard/assets/images/scholar/fire-mage.png`. The browser only
 * needs the part from `assets/` onward, served from the repository's shared
 * asset directory.
 */

/** Base URL the shared `assets/` directory is served from. */
export const ASSET_BASE =
  (import.meta.env.VITE_ASSET_BASE as string | undefined) ?? "/assets";

/**
 * Converts a card's `image_path` into a browser URL.
 *
 * Accepts the absolute paths produced by the Python factories, bare
 * `/images/...` texture paths from the card JSON, and values that are already
 * web URLs.
 *
 * @param imagePath - The card's `image_path`, possibly null.
 * @returns A URL the browser can load, falling back to the card back.
 */
export function resolveCardImage(imagePath: string | null | undefined): string {
  if (!imagePath) return cardBackUrl();

  if (/^https?:\/\//.test(imagePath)) return imagePath;

  const normalized = imagePath.replace(/\\/g, "/");
  const marker = normalized.lastIndexOf("assets/");
  if (marker >= 0) {
    return `${ASSET_BASE}/${normalized.slice(marker + "assets/".length)}`;
  }

  // Bare texture path straight out of monsterInfo.json etc.
  return `${ASSET_BASE}/${normalized.replace(/^\/+/, "")}`;
}

/** URL of the shared card back. */
export function cardBackUrl(): string {
  return `${ASSET_BASE}/card-back.png`;
}

/** URL of the empty card-preview plate. */
export function cardPreviewUrl(): string {
  return `${ASSET_BASE}/card-preview.png`;
}

/** URL of the deck/hand backdrop. */
export function deckUrl(): string {
  return `${ASSET_BASE}/deck.png`;
}

/** URL of the board background. */
export function backgroundUrl(): string {
  return `${ASSET_BASE}/background.png`;
}

/**
 * URL of the tile drawn under a field row.
 *
 * Matches `Matrix._setup_tile_mapping`: the top half of the board uses the
 * opponent tile, the bottom half the player tile.
 *
 * @param row - Row index in render coordinates.
 * @returns The tile image URL.
 */
export function tileUrl(row: number): string {
  return row < 2 ? `${ASSET_BASE}/tile1.png` : `${ASSET_BASE}/tile2.png`;
}
