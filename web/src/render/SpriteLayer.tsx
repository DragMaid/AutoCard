/**
 * Draws card sprites above the board.
 *
 * Each sprite mounts once and is then moved by the render loop writing
 * transforms directly to its node, so this component only re-renders when a
 * card's *appearance* changes (face-down, highlight, trap button).
 */

import { useCallback, useRef } from "react";

import type { GameClient } from "../game/gameClient";
import { OPPONENT_COLOR, PLAYER_COLOR } from "../game/layout";
import { isSpriteFaceDown, type Sprite } from "../game/sprites";
import { UI_FONT } from "../game/theme";
import { CardFace } from "./CardFace";

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
  //
  // Keyed by the sprite object rather than its card id, because a card being
  // played is briefly two sprites at once: the hand sprite still fading out and
  // the field sprite that replaced it. Sharing one closure between them bound
  // the field card's node to the dying hand sprite, so the summoned card was
  // never positioned and never appeared on the board. A WeakMap also drops
  // entries as sprites are collected, which the old id map never did.
  const outerRefs = useRef(new WeakMap<Sprite, (node: HTMLDivElement | null) => void>());
  const faceRefs = useRef(new WeakMap<Sprite, (node: HTMLDivElement | null) => void>());

  const bindOuter = useCallback((sprite: Sprite) => {
    let ref = outerRefs.current.get(sprite);
    if (!ref) {
      ref = (node: HTMLDivElement | null) => {
        sprite.el = node;
      };
      outerRefs.current.set(sprite, ref);
    }
    return ref;
  }, []);

  const bindFace = useCallback((sprite: Sprite) => {
    let ref = faceRefs.current.get(sprite);
    if (!ref) {
      ref = (node: HTMLDivElement | null) => {
        sprite.faceEl = node;
      };
      faceRefs.current.set(sprite, ref);
    }
    return ref;
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0">
      {sprites.map((sprite) => {
        const card = sprite.card;
        const faceDown = isSpriteFaceDown(sprite);
        const trapButton =
          card.card_type === "TRAP" &&
          card.triggerable &&
          !card.is_opponent &&
          sprite.zone === "matrix";

        const activated = client.state.gameState.activated_traps.includes(
          sprite.id,
        );

        // A hairline in the owner's colour is what tells the two sides apart
        // now that opponent cards are no longer drawn upside down.
        const ownerColor = card.is_opponent ? OPPONENT_COLOR : PLAYER_COLOR;

        return (
          <div
            // Zone-qualified: the same card can be mounted twice for a frame
            // while a hand sprite dies and its field sprite takes over, and a
            // duplicate key makes React drop one of the two nodes.
            key={`${sprite.zone}:${sprite.id}`}
            ref={bindOuter(sprite)}
            className="absolute left-0 top-0 will-change-transform"
            style={{ width: sprite.width, height: sprite.height }}
          >
            {/* Only the card surface rotates and squashes. */}
            <div
              ref={bindFace(sprite)}
              className="absolute inset-0"
              style={{
                transformOrigin: "center center",
                boxShadow: `0 0 0 2px ${ownerColor}, 3px 3px 0 rgba(0, 0, 0, 0.55)`,
              }}
            >
              <CardFace
                card={card}
                width={sprite.width}
                height={sprite.height}
                faceDown={faceDown}
              />
            </div>

            {/* Screen-space decorations, never rotated with the card. */}
            {sprite.highlight && (
              <div
                className="pointer-events-none absolute"
                style={{
                  inset: -4,
                  border: `3px solid ${sprite.highlightColor}`,
                  boxShadow: `0 0 0 1px rgba(0, 0, 0, 0.7)`,
                }}
              />
            )}

            {trapButton && (
              <div
                className="absolute left-0 right-0 flex items-center justify-center leading-none"
                style={{
                  bottom: -9,
                  height: 18,
                  fontFamily: UI_FONT,
                  fontSize: 8,
                  letterSpacing: "0.1em",
                  color: "#fff",
                  backgroundColor: activated ? "#2f8b45" : "#a8283a",
                  border: `2px solid ${activated ? "#7fe39b" : "#e0768a"}`,
                  boxShadow: "2px 2px 0 rgba(0, 0, 0, 0.6)",
                }}
              >
                {activated ? "ARMED" : "ARM"}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
