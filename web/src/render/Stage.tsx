/**
 * Fixed-resolution stage with uniform scaling.
 *
 * The whole board is laid out once against the 1280x720 design resolution, then
 * scaled to fit whatever space its host gives it. That keeps every slot, card
 * and panel position identical at any window size, and means the input layer
 * only ever deals in design pixels.
 *
 * The host is expected to be padded, so the stage is a framed object floating
 * on the starfield rather than something bleeding off the edges of the screen.
 *
 * The game is landscape-only: in portrait the stage is replaced by a prompt to
 * rotate, rather than reflowing into a layout the engine has no concept of.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { DESIGN_HEIGHT, DESIGN_WIDTH } from "../game/layout";
import { COLORS, UI_FONT, pixelPanel } from "../game/theme";

/** A pointer position already converted into design-space coordinates. */
export interface StagePointer {
  x: number;
  y: number;
  button: number;
}

export interface StageProps {
  children: ReactNode;
  onPointerDown?: (pointer: StagePointer) => void;
  onPointerMove?: (pointer: StagePointer) => void;
  onPointerUp?: (pointer: StagePointer) => void;
  onPointerCancel?: () => void;
}

/** Minimum aspect ratio treated as landscape. */
const LANDSCAPE_MIN_RATIO = 1;

/** Frame thickness in design pixels; scales with everything else. */
const FRAME = 6;

/**
 * Elements whose own click handling must survive a press on the stage.
 *
 * The board is driven by raw pointer coordinates, but the panels drawn over it
 * are ordinary DOM controls, and those need their clicks intact.
 */
const CONTROLS = "button, input, select, textarea, a, summary, label";

/**
 * Scales its children from design space to the host element.
 *
 * @param props - Children plus pointer callbacks receiving design-space points.
 * @returns The scaled stage, or a rotate prompt in portrait.
 */
export function Stage({
  children,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
}: StageProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [portrait, setPortrait] = useState(false);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const measure = () => {
      const { width, height } = host.getBoundingClientRect();
      if (width === 0 || height === 0) return;

      setPortrait(width / height < LANDSCAPE_MIN_RATIO);
      setScale(Math.min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    window.addEventListener("orientationchange", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("orientationchange", measure);
    };
  }, []);

  /** Converts a browser pointer event into design-space coordinates. */
  const toStage = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>): StagePointer => {
      const rect = stageRef.current?.getBoundingClientRect();
      if (!rect || scale === 0) {
        return { x: 0, y: 0, button: event.button };
      }
      return {
        x: (event.clientX - rect.left) / scale,
        y: (event.clientY - rect.top) / scale,
        button: event.button,
      };
    },
    [scale],
  );

  // Suppress the browser context menu so right-click can toggle a monster,
  // matching the pygame build's RIGHT_CLICK handling.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const block = (event: Event) => event.preventDefault();
    stage.addEventListener("contextmenu", block);
    return () => stage.removeEventListener("contextmenu", block);
  }, []);

  return (
    <div ref={hostRef} className="relative h-full w-full">
      {portrait && (
        <div className="absolute inset-0 z-50 flex items-center justify-center px-8">
          <div
            className="flex max-w-sm flex-col items-center gap-4 px-8 py-7 text-center"
            style={pixelPanel(COLORS.edge, 6)}
          >
            <span
              style={{
                fontFamily: UI_FONT,
                fontSize: 15,
                letterSpacing: "0.08em",
                color: COLORS.text,
              }}
            >
              ROTATE YOUR DEVICE
            </span>
            <p
              style={{
                fontFamily: UI_FONT,
                fontSize: 9,
                lineHeight: 1.8,
                color: COLORS.textDim,
              }}
            >
              AutoCard is played in landscape. Turn your device sideways to see
              the board.
            </p>
          </div>
        </div>
      )}

      <div
        ref={stageRef}
        className="absolute left-1/2 top-1/2 origin-center touch-none"
        style={{
          width: DESIGN_WIDTH,
          height: DESIGN_HEIGHT,
          transform: `translate(-50%, -50%) scale(${scale})`,
          visibility: portrait ? "hidden" : "visible",
          backgroundColor: "rgba(5, 5, 14, 0.55)",
          boxShadow: `0 0 0 ${FRAME}px #14122b, 0 0 0 ${FRAME + 3}px #4a4585,` +
            ` ${FRAME + 6}px ${FRAME + 6}px 0 rgba(0, 0, 0, 0.55)`,
        }}
        onPointerDown={(event) => {
          // Captured on the stage, not on the card under the cursor. A sprite
          // node can be unmounted mid-drag (its card leaves the hand), which
          // drops the capture and loses the release, leaving an attack arrow
          // stuck to the cursor. Capturing here also keeps a release outside
          // the stage — the common case, since the board fills it — addressed
          // to the element that knows how to finish the drag.
          //
          // Not for a press that lands on a control, though: capturing
          // re-targets the release to the stage, and a button whose press and
          // release land on different elements is never clicked. The rail's
          // End Turn and Surrender, and every overlay button, live inside this
          // element.
          if (!(event.target as Element).closest?.(CONTROLS)) {
            try {
              event.currentTarget.setPointerCapture?.(event.pointerId);
            } catch {
              // Throws if the pointer is already gone — a very fast click, or
              // a synthetic event. The press is still worth handling.
            }
          }
          onPointerDown?.(toStage(event));
        }}
        onPointerMove={(event) => onPointerMove?.(toStage(event))}
        onPointerUp={(event) => onPointerUp?.(toStage(event))}
        onPointerCancel={() => onPointerCancel?.()}
        // Belt and braces for the case where capture was never established,
        // e.g. a pointer that entered mid-gesture: leaving with no button held
        // ends the drag rather than letting an arrow trail a cursor that is
        // gone. A leave *while* a button is down is an ordinary drag past the
        // stage edge and must not cancel it.
        onPointerLeave={(event) => {
          if (event.buttons === 0) onPointerCancel?.();
        }}
      >
        {children}
      </div>
    </div>
  );
}
