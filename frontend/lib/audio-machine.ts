/** AudioPlayer state machine — pure reducer, exhaustively unit-tested.
 *
 * States: idle → loading → playing ⇄ paused; seek keeps the current
 * play/pause state; error from anywhere; reset back to idle.
 */

export type PlayerState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "playing"; position: number; duration: number; rate: Rate }
  | { status: "paused"; position: number; duration: number; rate: Rate }
  | { status: "error"; message: string };

export type Rate = 1 | 1.5 | 2;

export type PlayerEvent =
  | { type: "LOAD" }
  | { type: "LOADED"; duration: number }
  | { type: "PLAY" }
  | { type: "PAUSE" }
  | { type: "TICK"; position: number }
  | { type: "SEEK"; position: number }
  | { type: "SET_RATE"; rate: Rate }
  | { type: "ENDED" }
  | { type: "ERROR"; message: string }
  | { type: "RESET" };

export const initialPlayerState: PlayerState = { status: "idle" };

const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max);

export function playerReducer(
  state: PlayerState,
  event: PlayerEvent,
): PlayerState {
  switch (event.type) {
    case "LOAD":
      return state.status === "idle" || state.status === "error"
        ? { status: "loading" }
        : state;

    case "LOADED":
      return state.status === "loading"
        ? { status: "playing", position: 0, duration: event.duration, rate: 1 }
        : state;

    case "PLAY":
      return state.status === "paused"
        ? { ...state, status: "playing" }
        : state;

    case "PAUSE":
      return state.status === "playing"
        ? { ...state, status: "paused" }
        : state;

    case "TICK":
      return state.status === "playing"
        ? { ...state, position: clamp(event.position, state.duration) }
        : state;

    case "SEEK":
      return state.status === "playing" || state.status === "paused"
        ? { ...state, position: clamp(event.position, state.duration) }
        : state;

    case "SET_RATE":
      return state.status === "playing" || state.status === "paused"
        ? { ...state, rate: event.rate }
        : state;

    case "ENDED":
      return state.status === "playing"
        ? {
            status: "paused",
            position: state.duration,
            duration: state.duration,
            rate: state.rate,
          }
        : state;

    case "ERROR":
      return { status: "error", message: event.message };

    case "RESET":
      return initialPlayerState;

    default:
      return state;
  }
}
