/**
 * Draws card sprites above the board.
 *
 * Each sprite mounts once and is then moved by the render loop writing
 * transforms directly to its node, so this component only re-renders when a
 * card's *appearance* changes (face-down, highlight, trap button).
 */

import { useCallback, useRef } from "react";

import type { GameClient } from "../game/gameClient";
import { isSpriteFaceDown, type Sprite } from "../game/sprites";
import { CARD_FONT_FAMILY } from "../game/text";
import { CardFace, StatOverlay } from "./CardFace";

export interface SpriteLayerProps {
  client: GameClient;
  sprites: Sprite[];
}

/**
 * Renders every card sprite.
 *
 * @param props - The client and the sprites to mount.
 * @returns The sprite layer.
 */
export function SpriteLayer({ client, sprites }: SpriteLayerProps) {
  // Stable per-sprite ref callbacks: a fresh closure each render would make
  // React detach and re-attach every node on every frame.
  const outerRefs = useRef(new Map<string, (node: HTMLDivElement | null) => void>());
  const faceRefs = useRef(new Map<string, (node: HTMLDivElement | null) => void>());

  const bindOuter = useCallback((sprite: Sprite) => {
    let ref = outerRefs.current.get(sprite.id);
    if (!ref) {
      ref = (node: HTMLDivElement | null) => {
        sprite.el = node;
      };
      outerRefs.current.set(sprite.id, ref);
    }
    return ref;
  }, []);

  const bindFace = useCallback((sprite: Sprite) => {
    let ref = faceRefs.current.get(sprite.id);
    if (!ref) {
      ref = (node: HTMLDivElement | null) => {
        sprite.faceEl = node;
      };
      faceRefs.current.set(sprite.id, ref);
    }
    return ref;
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0">
      {sprites.map((sprite) => {
        const card = sprite.card;
        const faceDown = isSpriteFaceDown(sprite);
        const showStats = card.card_type === "MONSTER" && !faceDown;
        const trapButton =
          card.card_type === "TRAP" &&
          card.triggerable &&
          !card.is_opponent &&
          sprite.zone === "matrix";

        const activated = client.state.gameState.activated_traps.includes(
          sprite.id,
        );

        return (
          <div
            key={sprite.id}
            ref={bindOuter(sprite)}
            className="absolute left-0 top-0 will-change-transform"
            style={{ width: sprite.width, height: sprite.height }}
          >
            {/* Only the card surface rotates and squashes. */}
            <div
              ref={bindFace(sprite)}
              className="absolute inset-0"
              style={{ transformOrigin: "center center" }}
            >
              <CardFace
                card={card}
                width={sprite.width}
                height={sprite.height}
                faceDown={faceDown}
                flipped={sprite.flip}
              />
            </div>

            {/* Screen-space decorations, never rotated with the card. */}
            {sprite.highlight && (
              <div
                className="pointer-events-none absolute inset-0"
                style={{ border: `5px solid ${sprite.highlightColor}` }}
              />
            )}

            {showStats && (
              <StatOverlay
                card={card}
                position={card.is_opponent ? "below" : "above"}
              />
            )}

            {trapButton && (
              <div
                className="absolute left-0 right-0 flex items-center justify-center rounded-lg text-[11px] font-bold tracking-wide text-white"
                style={{
                  bottom: 10,
                  height: 30,
                  fontFamily: CARD_FONT_FAMILY,
                  backgroundColor: activated
                    ? "rgb(40, 167, 69)"
                    : "rgb(220, 53, 69)",
                }}
              >
                {activated ? "ACTIVATED" : "ACTIVATE"}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
