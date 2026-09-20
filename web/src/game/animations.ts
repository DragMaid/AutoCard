/**
 * Animation system, ported from `gui/animations/`.
 *
 * Each animation locks one or more sprites. A sprite runs at most one animation
 * at a time, and an animation only advances once it is at the head of every
 * queue it locks — the same scheduling `AnimationManager.update` performs in
 * Python, which is what keeps a two-card attack in step.
 */

import type { Sprite } from "./sprites";
import type { SpriteManager } from "./sprites";

/** Eases used by the ported animations. */
const easeIn = (x: number) => x * x;
const easeOut = (x: number) => 1 - (1 - x) * (1 - x);
const smoothstep = (x: number) => x * x * (3 - 2 * x);
const easeInOutQuad = (x: number) =>
  x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Signed angle between a vector and a facing direction, in degrees. */
function signedAngle(
  vx: number,
  vy: number,
  fx: number,
  fy: number,
): number {
  const vlen = Math.hypot(vx, vy) || 1;
  const flen = Math.hypot(fx, fy) || 1;
  const nx = vx / vlen;
  const ny = vy / vlen;
  const gx = fx / flen;
  const gy = fy / flen;
  return (Math.atan2(gx * ny - gy * nx, gx * nx + gy * ny) * 180) / Math.PI;
}

/** Base class for a timed animation over a set of sprites. */
export abstract class Animation {
  elapsed = 0;
  finished = false;

  /**
   * @param locks - Sprites this animation controls exclusively.
   * @param duration - Runtime in seconds; zero completes immediately.
   */
  constructor(
    readonly locks: Sprite[],
    readonly duration: number,
  ) {}

  /** Advances the animation, returning true once it has completed. */
  update(dt: number): boolean {
    this.elapsed += dt;
    const t = this.duration <= 0 ? 1 : Math.min(this.elapsed / this.duration, 1);
    this.apply(t);
    if (t >= 1) this.finished = true;
    return this.finished;
  }

  /** Applies the animation at normalized progress `t`. */
  protected abstract apply(t: number): void;
}

/** Slides a sprite between two points (card draw). */
export class MoveAnimation extends Animation {
  constructor(
    private sprite: Sprite,
    private from: [number, number],
    private to: [number, number],
    duration: number,
  ) {
    super([sprite], duration);
  }

  protected apply(t: number): void {
    const p = easeInOutQuad(t);
    this.sprite.x = lerp(this.from[0], this.to[0], p);
    this.sprite.y = lerp(this.from[1], this.to[1], p);
  }
}

/** Drops a sprite onto its slot with a squash on landing. */
export class PlaceAnimation extends Animation {
  private readonly from: [number, number];

  constructor(
    private sprite: Sprite,
    private to: [number, number],
    duration: number,
  ) {
    super([sprite], duration);
    this.from = [to[0], to[1] - 100];
  }

  protected apply(t: number): void {
    const p = smoothstep(t);
    this.sprite.x = lerp(this.from[0], this.to[0], p);
    this.sprite.y = lerp(this.from[1], this.to[1], p);
    this.sprite.scaleY =
      t < 0.95 ? 1 : 1 - 0.2 * Math.sin(((t - 0.95) / 0.05) * Math.PI);
  }
}

/** Fades a sprite out, then hands control back so it can be removed. */
export class DeathAnimation extends Animation {
  constructor(
    private sprite: Sprite,
    duration: number,
    private onFinish: () => void,
  ) {
    super([sprite], duration);
  }

  protected apply(t: number): void {
    this.sprite.alpha = 1 - t;
  }

  override update(dt: number): boolean {
    const done = super.update(dt);
    if (done) this.onFinish();
    return done;
  }
}

/** Rotates a monster between attack and defence orientation. */
export class ToggleRotateAnimation extends Animation {
  private callbackDone = false;

  constructor(
    private sprite: Sprite,
    private startAngle: number,
    private endAngle: number,
    duration: number,
    private onFinished?: () => void,
  ) {
    super([sprite], duration);
  }

  protected apply(t: number): void {
    this.sprite.angle = lerp(this.startAngle, this.endAngle, smoothstep(t));
    if (t >= 0.8 && !this.callbackDone) {
      this.callbackDone = true;
      this.onFinished?.();
    }
  }
}

/** Two monsters lunge at each other and bounce back. */
export class AttackAnimation extends Animation {
  private readonly start1: [number, number];
  private readonly start2: [number, number];
  private readonly mid: [number, number];
  private readonly finalAngle1: number;
  private readonly finalAngle2: number;
  private readonly startAngle1: number;
  private readonly startAngle2: number;
  private impactDone = false;

  constructor(
    private card1: Sprite,
    private card2: Sprite,
    duration: number,
    private onImpact?: (x: number, y: number) => void,
  ) {
    super([card1, card2], duration);
    this.start1 = [card1.homeX, card1.homeY];
    this.start2 = [card2.homeX, card2.homeY];
    this.mid = [
      (this.start1[0] + this.start2[0]) / 2,
      (this.start1[1] + this.start2[1]) / 2,
    ];

    // Each card turns to face its target, relative to the side it plays from.
    const facing1 = card1.card.is_opponent ? 1 : -1;
    this.finalAngle1 = signedAngle(
      this.start2[0] - this.start1[0],
      this.start2[1] - this.start1[1],
      0,
      facing1,
    );
    const facing2 = card2.card.is_opponent ? 1 : -1;
    this.finalAngle2 = signedAngle(
      this.start1[0] - this.start2[0],
      this.start1[1] - this.start2[1],
      0,
      facing2,
    );

    this.startAngle1 =
      "mode" in card1.card && card1.card.mode === "DEFEND" ? 90 : 0;
    this.startAngle2 =
      "mode" in card2.card && card2.card.mode === "DEFEND" ? 90 : 0;
  }

  protected apply(t: number): void {
    if (t < 0.5) {
      const p = easeIn(t / 0.5);
      this.card1.x = lerp(this.start1[0], this.mid[0], p * 0.6);
      this.card1.y = lerp(this.start1[1], this.mid[1], p * 0.6);
      this.card2.x = lerp(this.start2[0], this.mid[0], p * 0.6);
      this.card2.y = lerp(this.start2[1], this.mid[1], p * 0.6);
      this.card1.angle = lerp(this.startAngle1, this.finalAngle1, p);
      this.card2.angle = lerp(this.startAngle2, this.finalAngle2, p);
    } else {
      const p = easeOut((t - 0.5) / 0.5);
      this.card1.x = lerp(this.mid[0], this.start1[0], p);
      this.card1.y = lerp(this.mid[1], this.start1[1], p);
      this.card2.x = lerp(this.mid[0], this.start2[0], p);
      this.card2.y = lerp(this.mid[1], this.start2[1], p);

      if (!this.impactDone) {
        this.impactDone = true;
        this.onImpact?.(this.mid[0], this.mid[1]);
        this.card1.angle = this.finalAngle1;
        this.card2.angle = this.finalAngle2;
      }

      for (const card of [this.card1, this.card2]) {
        card.scaleX = 1.1 - 0.1 * p;
        card.scaleY = 0.9 + 0.1 * p;
      }
    }

    if (t >= 1) {
      this.card1.angle = this.startAngle1;
      this.card2.angle = this.startAngle2;
      this.card1.x = this.start1[0];
      this.card1.y = this.start1[1];
      this.card2.x = this.start2[0];
      this.card2.y = this.start2[1];
      this.card1.scaleX = this.card1.scaleY = 1;
      this.card2.scaleX = this.card2.scaleY = 1;
    }
  }
}

/** A monster lunges at the opposing player's hand area. */
export class AttackPlayerAnimation extends Animation {
  private readonly start: [number, number];
  private readonly startAngle: number;
  private readonly finalAngle: number;
  private impactDone = false;

  constructor(
    private card: Sprite,
    private target: [number, number],
    duration: number,
    private onImpact?: (x: number, y: number) => void,
  ) {
    super([card], duration);
    this.start = [card.homeX, card.homeY];
    this.startAngle = card.angle;
    const facing = card.card.is_opponent ? 1 : -1;
    this.finalAngle = signedAngle(
      target[0] - this.start[0],
      target[1] - this.start[1],
      0,
      facing,
    );
  }

  protected apply(t: number): void {
    if (t < 0.5) {
      const p = easeIn(t / 0.5);
      this.card.x = lerp(this.start[0], this.target[0], p);
      this.card.y = lerp(this.start[1], this.target[1], p);
      this.card.angle = lerp(this.startAngle, this.finalAngle, p);
    } else {
      const p = easeOut((t - 0.5) / 0.5);
      this.card.x = lerp(this.target[0], this.start[0], p);
      this.card.y = lerp(this.target[1], this.start[1], p);

      if (!this.impactDone) {
        this.impactDone = true;
        this.onImpact?.(this.target[0], this.target[1]);
      }
      this.card.scaleX = 1.1 - 0.1 * p;
      this.card.scaleY = 0.9 + 0.1 * p;
    }

    if (t >= 1) {
      this.card.angle = this.startAngle;
      this.card.x = this.start[0];
      this.card.y = this.start[1];
      this.card.scaleX = this.card.scaleY = 1;
    }
  }
}

/** Two monsters lean together and fade as their upgrade appears. */
export class MergeAnimation extends Animation {
  private readonly start1: [number, number];
  private readonly start2: [number, number];
  private readonly mid: [number, number];
  private impactDone = false;

  constructor(
    private card1: Sprite,
    private card2: Sprite,
    private result: Sprite,
    duration: number,
    private onImpact?: (x: number, y: number) => void,
    private onFinish?: (result: Sprite) => void,
  ) {
    super([card1, card2], duration);
    this.start1 = [card1.x, card1.y];
    this.start2 = [card2.x, card2.y];
    this.mid = [
      (this.start1[0] + this.start2[0]) / 2,
      (this.start1[1] + this.start2[1]) / 2,
    ];
    this.result.alpha = 0;
  }

  protected apply(t: number): void {
    const p = smoothstep(t);
    const lean = 0.3;

    this.card1.x = lerp(this.start1[0], this.mid[0], p * lean);
    this.card1.y = lerp(this.start1[1], this.mid[1], p * lean);
    this.card2.x = lerp(this.start2[0], this.mid[0], p * lean);
    this.card2.y = lerp(this.start2[1], this.mid[1], p * lean);

    this.card1.alpha = 1 - p;
    this.card2.alpha = 1 - p;

    if (!this.impactDone && t >= 0.8) {
      this.impactDone = true;
      this.onImpact?.(this.mid[0], this.mid[1]);
    }

    if (t >= 1) {
      this.result.alpha = 1;
      this.onFinish?.(this.result);
    }
  }
}

/** Flips a trap face-up, glows, then shakes it. */
export class TrapTriggerAnimation extends Animation {
  private readonly start: [number, number];
  private glowDone = false;

  constructor(
    private card: Sprite,
    duration: number,
    private onGlow?: (x: number, y: number) => void,
  ) {
    super([card], duration);
    this.start = [card.x, card.y];
  }

  protected apply(t: number): void {
    if (t < 0.3) {
      const p = t / 0.3;
      this.card.scaleY = Math.max(0.01, Math.abs(Math.cos(p * Math.PI)));
      if (p >= 0.5) this.card.faceDownOverride = false;
    } else {
      this.card.faceDownOverride = false;
      this.card.scaleY = 1;
    }

    if (t >= 0.3 && !this.glowDone) {
      this.glowDone = true;
      this.onGlow?.(this.start[0], this.start[1]);
    }

    if (t >= 0.6) {
      const p = (t - 0.6) / 0.4;
      this.card.x = this.start[0] + Math.sin(p * 20 * Math.PI) * 5 * (1 - p);
      this.card.y = this.start[1];
    }

    if (t >= 1) {
      this.card.x = this.start[0];
      this.card.scaleY = 1;
    }
  }
}

/** Pulses a trap to show the owner it may be activated. */
export class TrapTriggerableAnimation extends Animation {
  constructor(
    private card: Sprite,
    duration: number,
  ) {
    super([card], duration);
  }

  protected apply(t: number): void {
    this.card.scaleY = 1 + Math.sin(t * Math.PI) * 0.05;
    if (t >= 1) this.card.scaleY = 1;
  }
}

/** Pops and settles a spell as it resolves. */
export class SpellAnimation extends Animation {
  constructor(
    private card: Sprite,
    duration: number,
    private onGlow?: (x: number, y: number) => void,
  ) {
    super([card], duration);
  }

  private glowDone = false;

  protected apply(t: number): void {
    if (t < 0.3) {
      const p = easeOut(t / 0.3);
      this.card.offsetY = -20 * p;
      this.card.scaleX = 1 + 0.3 * p;
      this.card.scaleY = 1 + 0.3 * p;
      this.card.angle = 15 * Math.sin(p * Math.PI * 2);
    }

    if (t >= 0.3 && !this.glowDone) {
      this.glowDone = true;
      this.onGlow?.(this.card.x, this.card.y);
    }

    if (t >= 0.6) {
      const p = smoothstep((t - 0.6) / 0.4);
      this.card.offsetY = -20 * (1 - p);
      this.card.scaleX = 1 + 0.3 * (1 - p);
      this.card.scaleY = 1 + 0.3 * (1 - p);
      this.card.angle = 0;
    }

    if (t >= 1) {
      this.card.offsetY = 0;
      this.card.scaleX = 1;
      this.card.scaleY = 1;
      this.card.angle = 0;
    }
  }
}

/** Per-sprite FIFO queue, ported from `gui/animations/queue.py`. */
class AnimationQueue {
  private items: Animation[] = [];

  /** Appends an animation unless the sprite is already dying. */
  add(animation: Animation): void {
    if (this.items.at(-1) instanceof DeathAnimation) return;
    this.items.push(animation);
  }

  peek(): Animation | undefined {
    return this.items[0];
  }

  pop(): Animation | undefined {
    return this.items.shift();
  }

  get length(): number {
    return this.items.length;
  }
}

/** A transient visual burst, standing in for `gui/effects`. */
export interface VisualEffect {
  id: number;
  kind: "slam" | "merge" | "trap-glow" | "trap-pulse" | "spell-glow" | "hit-player";
  x: number;
  y: number;
  born: number;
  duration: number;
}

/**
 * Schedules animations across sprites.
 *
 * Ported from `gui/animations/manager.py`, including its rule that an animation
 * only advances when it sits at the head of every queue it locks.
 */
export class AnimationManager {
  private readonly queues = new Map<Sprite, AnimationQueue>();
  private readonly animating = new Map<Sprite, Set<string>>();

  /** Visual bursts spawned by animations, consumed by the renderer. */
  effects: VisualEffect[] = [];
  private effectId = 0;

  /** True while any animation is queued or running. */
  get running(): boolean {
    for (const queue of this.queues.values()) if (queue.length) return true;
    return false;
  }

  /** Returns whether a sprite is running an animation of the given class. */
  isAnimating(sprite: Sprite, kind?: string): boolean {
    const active = this.animating.get(sprite);
    if (!active) return false;
    return kind ? active.has(kind) : active.size > 0;
  }

  /** Spawns a short-lived visual burst at a point. */
  spawn(kind: VisualEffect["kind"], x: number, y: number): void {
    this.effectId += 1;
    this.effects.push({
      id: this.effectId,
      kind,
      x,
      y,
      born: performance.now(),
      duration: kind === "slam" ? 350 : 600,
    });
  }

  /**
   * Queues an animation, skipping duplicates of the same kind on a sprite.
   *
   * @param animation - The animation to schedule.
   */
  add(animation: Animation): void {
    const kind = animation.constructor.name;
    for (const sprite of animation.locks) {
      if (this.animating.get(sprite)?.has(kind)) return;
    }
    for (const sprite of animation.locks) {
      let active = this.animating.get(sprite);
      if (!active) {
        active = new Set();
        this.animating.set(sprite, active);
      }
      active.add(kind);

      let queue = this.queues.get(sprite);
      if (!queue) {
        queue = new AnimationQueue();
        this.queues.set(sprite, queue);
      }
      queue.add(animation);
    }
  }

  /**
   * Advances every animation that is ready.
   *
   * @param dt - Seconds since the previous frame.
   */
  update(dt: number): void {
    const heads = new Set<Animation>();
    for (const queue of this.queues.values()) {
      const head = queue.peek();
      if (head) heads.add(head);
    }

    const done: Animation[] = [];
    for (const animation of heads) {
      const ready = animation.locks.every(
        (sprite) => this.queues.get(sprite)?.peek() === animation,
      );
      if (ready && animation.update(dt)) done.push(animation);
    }

    for (const animation of done) {
      const kind = animation.constructor.name;
      for (const sprite of animation.locks) {
        this.animating.get(sprite)?.delete(kind);
        const queue = this.queues.get(sprite);
        if (queue?.peek() === animation) queue.pop();
        if (queue && queue.length === 0) this.queues.delete(sprite);
      }
    }

    const now = performance.now();
    this.effects = this.effects.filter(
      (effect) => now - effect.born < effect.duration,
    );
  }

  /** Drops every queued animation, used when the board is rebuilt. */
  clear(): void {
    this.queues.clear();
    this.animating.clear();
    this.effects = [];
  }

  // --- convenience creators, mirroring the Python manager -----------------

  createDeathAnimation(
    cardId: string,
    zone: "hand" | "matrix",
    sprites: SpriteManager,
    duration = 0.2,
  ): void {
    const sprite = sprites.zones[zone].get(cardId);
    if (!sprite) return;
    this.add(
      new DeathAnimation(sprite, duration, () => sprites.remove(cardId, zone)),
    );
  }

  createDrawAnimation(sprite: Sprite, from: [number, number], duration = 0.3): void {
    this.add(new MoveAnimation(sprite, from, [sprite.x, sprite.y], duration));
  }

  createPlaceAnimation(sprite: Sprite, duration = 0.5): void {
    this.add(new PlaceAnimation(sprite, [sprite.x, sprite.y], duration));
  }

  createAttackAnimation(a: Sprite, b: Sprite, duration = 1): void {
    this.add(
      new AttackAnimation(a, b, duration, (x, y) => this.spawn("slam", x, y)),
    );
  }

  createAttackPlayerAnimation(
    sprite: Sprite,
    target: [number, number],
    duration = 0.6,
  ): void {
    this.add(
      new AttackPlayerAnimation(sprite, target, duration, (x, y) => {
        this.spawn("hit-player", x, y);
        this.spawn("slam", x, y);
      }),
    );
  }

  createMergeAnimation(
    a: Sprite,
    b: Sprite,
    result: Sprite,
    duration = 1,
  ): void {
    this.add(
      new MergeAnimation(
        a,
        b,
        result,
        duration,
        (x, y) => this.spawn("merge", x, y),
        (sprite) => this.createPlaceAnimation(sprite),
      ),
    );
  }

  createToggleAnimation(sprite: Sprite, mode: string, duration = 0.3): void {
    const toAttack = mode === "ATTACK";
    this.add(
      new ToggleRotateAnimation(
        sprite,
        toAttack ? 90 : 0,
        toAttack ? 0 : 90,
        duration,
      ),
    );
  }

  createTriggerAnimation(sprite: Sprite, duration = 1): void {
    this.add(
      new TrapTriggerAnimation(sprite, duration, (x, y) =>
        this.spawn("trap-glow", x, y),
      ),
    );
  }

  createTriggerableAnimation(sprite: Sprite, duration = 0.8): void {
    this.add(new TrapTriggerableAnimation(sprite, duration));
  }

  createSpellAnimation(sprite: Sprite, duration = 0.2): void {
    this.add(
      new SpellAnimation(sprite, duration, (x, y) =>
        this.spawn("spell-glow", x, y),
      ),
    );
  }
}
