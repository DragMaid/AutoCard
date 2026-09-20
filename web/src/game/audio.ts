/**
 * Sound playback, ported from `gui/audio.py`.
 *
 * Keeps the Python manager's two guards: a short cooldown per file, and a
 * refusal to restart a clip that is still playing, which together stop a burst
 * of events from stacking the same sound on top of itself.
 *
 * Browsers block audio until the page has seen a user gesture, which pygame has
 * no equivalent for: playback stays muted until the first pointer or key press,
 * and the clips are fetched at that point.
 */

import { ASSET_BASE } from "./assets";

/** Clips under `assets/sounds/`, keyed by the name animations refer to. */
export const SOUNDS = {
  buttonPress: "button-press.mp3",
  cardDisappear: "card-disappear.mp3",
  cardDraw: "card-draw.mp3",
  merge: "merge.mp3",
  playerHurt: "player-hurt.mp3",
  shieldGuard: "shield-guard.mp3",
  spellActivate: "spell-activate.mp3",
  swordClash: "sword-clash.mp3",
  swordSlice: "sword-slice.mp3",
  trapReveal: "trap-reveal.mp3",
  trapTriggerable: "trap-triggerable.mp3",
} as const;

export type SoundName = keyof typeof SOUNDS;

/** Matches `AudioManager.sound.set_volume(0.3)`. */
const VOLUME = 0.3;

/** Matches `AudioManager.cooldown`, in milliseconds. */
const COOLDOWN_MS = 80;

const elements = new Map<SoundName, HTMLAudioElement>();
const lastPlayed = new Map<SoundName, number>();

let unlocked = false;
let listening = false;

/** Builds (and caches) the element backing a clip. */
function element(name: SoundName): HTMLAudioElement {
  let audio = elements.get(name);
  if (!audio) {
    audio = new Audio(`${ASSET_BASE}/sounds/${SOUNDS[name]}`);
    audio.preload = "auto";
    audio.volume = VOLUME;
    elements.set(name, audio);
  }
  return audio;
}

/** Fetches every clip so the first play of each is not silent. */
function preload(): void {
  for (const name of Object.keys(SOUNDS) as SoundName[]) element(name).load();
}

/**
 * Plays a clip, doing nothing until the page has been interacted with.
 *
 * @param name - Which clip to play.
 */
export function playSound(name: SoundName): void {
  if (!unlocked) return;

  const now = performance.now();
  if (now - (lastPlayed.get(name) ?? -Infinity) < COOLDOWN_MS) return;

  const audio = element(name);
  // Python holds one channel per file and skips while it is busy.
  if (!audio.paused && !audio.ended) return;

  lastPlayed.set(name, now);
  audio.currentTime = 0;
  // Autoplay policies reject rather than throw; a refused clip is not an error.
  void audio.play().catch(() => {});
}

/**
 * Arms audio on the first user gesture and plays UI buttons.
 *
 * The delegated `button` handler stands in for `Button.handle_event` in
 * `gui/screen/components.py`, which plays the press sound for every button.
 *
 * @returns A teardown function removing the listeners.
 */
export function installAudio(): () => void {
  if (listening) return () => {};
  listening = true;

  const unlock = () => {
    if (unlocked) return;
    unlocked = true;
    preload();
  };

  const onPointerDown = (event: PointerEvent) => {
    unlock();
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("button");
    if (button && !button.disabled) playSound("buttonPress");
  };

  window.addEventListener("pointerdown", onPointerDown, { capture: true });
  window.addEventListener("keydown", unlock, { capture: true });

  return () => {
    listening = false;
    window.removeEventListener("pointerdown", onPointerDown, { capture: true });
    window.removeEventListener("keydown", unlock, { capture: true });
  };
}
