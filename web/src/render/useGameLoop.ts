/**
 * The render loop.
 *
 * Runs `GameClient.frame` on every animation frame and writes sprite transforms
 * straight to the DOM. React is only re-rendered when something structural
 * changes — a card entering or leaving, a highlight toggling, a HUD value
 * moving — which keeps 60fps animation off the reconciler.
 */

import { useEffect, useRef, useState } from "react";

import type { GameClient, HudSnapshot } from "../game/gameClient";
import type { Sprite } from "../game/sprites";

/**
 * Applies a sprite's animation state to its DOM nodes.
 *
 * Position and opacity go on the outer node; rotation and squash go on the
 * inner face node only. That mirrors pygame, where the stat line, merge
 * highlight and trap button are blitted in screen space around the card's
 * bounding box rather than being part of the rotated card surface.
 */
function paint(sprite: Sprite): void {
  const el = sprite.el;
  if (!el) return;

  const x = sprite.x - sprite.width / 2;
  const y = sprite.y - sprite.height / 2 + sprite.offsetY;

  el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  el.style.opacity = String(sprite.alpha);
  el.style.zIndex = String(
    sprite.dragging ? 1000 : sprite.zone === "hand" ? 20 : 10,
  );

  if (sprite.faceEl) {
    sprite.faceEl.style.transform =
      `rotate(${sprite.angle}deg) scale(${sprite.scaleX}, ${sprite.scaleY})`;
  }
}

/**
 * Builds a cheap signature of everything that requires a React re-render.
 *
 * Position and rotation are deliberately excluded: those are painted directly.
 */
function signature(sprites: Sprite[]): string {
  let out = "";
  for (const sprite of sprites) {
    const card = sprite.card;
    out += `${sprite.id}:${sprite.zone}:${sprite.highlight ? 1 : 0}:${sprite.highlightColor}:`;
    out += `${card.is_face_down ? 1 : 0}:${sprite.faceDownOverride ?? "-"}:`;
    out += card.card_type === "TRAP" ? `${card.triggerable ? 1 : 0}` : "0";
    out += "|";
  }
  return out;
}

export interface GameLoopResult {
  /** Sprites to mount, in a stable draw order. */
  sprites: Sprite[];
  /** Current HUD values. */
  hud: HudSnapshot;
  /** Increments while arrows are on screen, to re-render the arrow layer. */
  arrowTick: number;
  /** Last error reported by the connection or server. */
  error: string | null;
}

/**
 * Drives the render loop for a game client.
 *
 * @param client - The client whose match to render.
 * @returns The React-visible slice of the client's state.
 */
export function useGameLoop(client: GameClient): GameLoopResult {
  const [sprites, setSprites] = useState<Sprite[]>([]);
  const [hud, setHud] = useState<HudSnapshot>(() => client.hud());
  const [arrowTick, setArrowTick] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const lastSignature = useRef("");
  const lastHud = useRef("");
  const lastTime = useRef(performance.now());
  /** Whether the previous frame drew any arrows or effects. */
  const hadArrows = useRef(false);

  useEffect(() => {
    let frameId = 0;

    const tick = (now: number) => {
      // Clamp dt so a backgrounded tab does not fast-forward every animation.
      const dt = Math.min((now - lastTime.current) / 1000, 0.05);
      lastTime.current = now;

      client.frame(dt);

      const all = [
        ...client.render.sprites.zones.matrix.values(),
        ...client.render.sprites.zones.hand.values(),
      ];

      for (const sprite of all) paint(sprite);

      const nextSignature = signature(all);
      if (nextSignature !== lastSignature.current) {
        lastSignature.current = nextSignature;
        setSprites(all);
      }

      const nextHud = client.hud();
      const hudKey = JSON.stringify(nextHud);
      if (hudKey !== lastHud.current) {
        lastHud.current = hudKey;
        setHud(nextHud);
      }

      // The arrow layer reads straight off the client, so it only repaints when
      // this counter moves. Ticking one extra frame *after* the last arrow goes
      // away is what erases it: stopping the moment the arrow is gone leaves
      // the previous render — and its arrow — on screen until something else
      // happens to re-render the tree.
      const arrows =
        client.input.dragArrow !== null ||
        client.render.attackIndicators.length > 0 ||
        client.render.animations.effects.length > 0;

      if (arrows || hadArrows.current) {
        setArrowTick((value) => (value + 1) % 1_000_000);
      }
      hadArrows.current = arrows;

      setError((current) =>
        current === client.lastError ? current : client.lastError,
      );

      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [client]);

  // Structural pushes from the network (seat assignment, patches).
  useEffect(() => {
    return client.subscribe(() => {
      lastSignature.current = "";
      setError(client.lastError);

      // The HUD is refreshed here as well as in the frame loop, because
      // patches keep arriving in a tab the browser has stopped animating.
      // Leaving it to `requestAnimationFrame` meant a backgrounded tab sat on
      // the turn it last saw — showing the opponent's turn, with End Turn
      // greyed out, on a board where it was your move.
      const next = client.hud();
      const key = JSON.stringify(next);
      if (key !== lastHud.current) {
        lastHud.current = key;
        setHud(next);
      }
    });
  }, [client]);

  return { sprites, hud, arrowTick, error };
}
