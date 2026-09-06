/**
 * Fixed-resolution stage with uniform scaling.
 *
 * The whole board is laid out once against the 1280x720 design resolution the
 * pygame build uses, then scaled to fit the viewport. That keeps every slot,
 * card and hand position identical to the desktop client at any window size,
 * and means the input layer only ever deals in design pixels.
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

/**
 * Scales its children from design space to the viewport.
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
    <div
      ref={hostRef}
      className="relative h-full w-full overflow-hidden bg-black"
    >
      {portrait && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-slate-950 px-8 text-center">
          <div className="text-5xl" aria-hidden>
            ⟳
          </div>
          <h2 className="text-xl font-semibold text-slate-100">
            Rotate your device
          </h2>
          <p className="max-w-xs text-sm text-slate-400">
            AutoCard is played in landscape. Turn your device sideways to see the
            board.
          </p>
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
        }}
        onPointerDown={(event) => {
          (event.target as Element).setPointerCapture?.(event.pointerId);
          onPointerDown?.(toStage(event));
        }}
        onPointerMove={(event) => onPointerMove?.(toStage(event))}
        onPointerUp={(event) => onPointerUp?.(toStage(event))}
        onPointerCancel={() => onPointerCancel?.()}
      >
        {children}
      </div>
    </div>
  );
}
