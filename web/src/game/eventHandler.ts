/**
 * Port of `core/gui/event_handler.py`.
 *
 * The authoritative engine ships animation events alongside each patch. This
 * handler turns them into animations, and defers merges until all three sprites
 * (both sources and the upgraded result) exist, exactly as the Python version
 * does through `RenderEngine.process_pending_merges`.
 */

import type { AnimationManager } from "./animations";
import { center, LAYOUT } from "./layout";
import type { SpriteManager } from "./sprites";
import type { GameState, MergeEvent } from "../types/game";
import { eventKind } from "../types/game";

/** Routes serialized game events to animations. */
export class EventHandler {
  /** Merge events waiting for their result sprite to be registered. */
  pendingMerges: MergeEvent[] = [];

  /**
   * @param sprites - Sprite registry to resolve event targets against.
   * @param animations - Animation manager to schedule onto.
   * @param onPreviewCard - Called to push a card into the preview panel.
   */
  constructor(
    private sprites: SpriteManager,
    private animations: AnimationManager,
    private onPreviewCard: (cardId: string) => void,
  ) {}

  /**
   * Consumes queued events and schedules their animations.
   *
   * @param events - Events drained from the client state.
   * @param state - Current game state, used to locate players.
   */
  handleEvents(events: Record<string, unknown>[], state: GameState): void {
    for (const event of events) {
      try {
        this.handleEvent(event, state);
      } catch (error) {
        console.error("handleEvents failed", error);
      }
    }
  }

  /** Dispatches a single event by its structural kind. */
  private handleEvent(
    event: Record<string, unknown>,
    state: GameState,
  ): void {
    switch (eventKind(event)) {
      case "ATTACK":
        this.handleAttack(event, state);
        break;
      case "TRAP_TRIGGER":
        this.handleTrapTrigger(event);
        break;
      case "TRAP_TRIGGERABLE":
        this.handleTrapTriggerable(event);
        break;
      case "TOGGLE":
        this.handleToggle(event);
        break;
      case "SPELL_ACTIVE":
        this.handleSpellActive(event);
        break;
      case "MERGE":
        this.pendingMerges.push(event as unknown as MergeEvent);
        break;
      default:
        break;
    }
  }

  /** Lunges the attacker at a card, or at the defending player's hand. */
  private handleAttack(
    event: Record<string, unknown>,
    state: GameState,
  ): void {
    const attacker = this.sprites.get(String(event.card_id));
    if (!attacker) return;

    if (event.target_is_player) {
      const target = state.players.find((p) => p.id === event.target_id);
      if (!target) return;
      const rect = target.is_opponent
        ? LAYOUT.areas.opponentHand
        : LAYOUT.areas.myHand;
      const point = center(rect);
      this.animations.createAttackPlayerAnimation(attacker, [point.x, point.y]);
      return;
    }

    const target = this.sprites.get(String(event.target_id));
    if (target) this.animations.createAttackAnimation(attacker, target);
  }

  /** Reveals a trap and shows it in the preview panel. */
  private handleTrapTrigger(event: Record<string, unknown>): void {
    const trap = this.sprites.get(String(event.card_id));
    if (!trap) return;
    this.animations.createTriggerAnimation(trap);
    this.onPreviewCard(String(event.card_id));
  }

  /** Pulses a trap that has become activatable. */
  private handleTrapTriggerable(event: Record<string, unknown>): void {
    const trap = this.sprites.get(String(event.card_id));
    if (trap) this.animations.createTriggerableAnimation(trap);
  }

  /** Rotates a monster into its new battle position. */
  private handleToggle(event: Record<string, unknown>): void {
    const card = this.sprites.get(String(event.card_id));
    if (card) this.animations.createToggleAnimation(card, String(event.mode));
  }

  /** Pops a spell as it resolves. */
  private handleSpellActive(event: Record<string, unknown>): void {
    const spell = this.sprites.get(String(event.spell_id));
    if (spell) this.animations.createSpellAnimation(spell);
  }

  /**
   * Starts merge animations whose participants have all been registered.
   *
   * Mirrors `RenderEngine.process_pending_merges`.
   */
  processPendingMerges(): void {
    const stillPending: MergeEvent[] = [];

    for (const event of this.pendingMerges) {
      const source = this.sprites.zones.matrix.get(event.card_id);
      const target = this.sprites.zones.matrix.get(event.target_id);
      const result = this.sprites.zones.matrix.get(event.result_card_id);

      if (source && target && result) {
        this.animations.createMergeAnimation(source, target, result);
      } else {
        stillPending.push(event);
      }
    }

    this.pendingMerges = stillPending;
  }

  /**
   * Whether a card is part of a merge that has not played yet.
   *
   * Such cards must not fade out through a death animation; the merge animation
   * owns their exit instead.
   */
  isPendingMerge(cardId: string): boolean {
    return this.pendingMerges.some(
      (event) =>
        event.card_id === cardId ||
        event.target_id === cardId ||
        event.result_card_id === cardId,
    );
  }
}
