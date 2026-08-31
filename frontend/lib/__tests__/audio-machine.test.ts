import { describe, expect, it } from "vitest";

import {
  initialPlayerState,
  playerReducer,
  type PlayerEvent,
  type PlayerState,
} from "@/lib/audio-machine";

function run(
  events: PlayerEvent[],
  from: PlayerState = initialPlayerState,
): PlayerState {
  return events.reduce(playerReducer, from);
}

describe("player state machine", () => {
  it("idle → loading → playing on LOAD/LOADED", () => {
    expect(run([{ type: "LOAD" }])).toEqual({ status: "loading" });
    expect(run([{ type: "LOAD" }, { type: "LOADED", duration: 47 }])).toEqual({
      status: "playing",
      position: 0,
      duration: 47,
      rate: 1,
    });
  });

  it("playing ⇄ paused", () => {
    const playing = run([{ type: "LOAD" }, { type: "LOADED", duration: 10 }]);
    const paused = playerReducer(playing, { type: "PAUSE" });
    expect(paused.status).toBe("paused");
    expect(playerReducer(paused, { type: "PLAY" }).status).toBe("playing");
  });

  it("TICK advances only while playing and clamps to duration", () => {
    const playing = run([{ type: "LOAD" }, { type: "LOADED", duration: 10 }]);
    expect(playerReducer(playing, { type: "TICK", position: 4 })).toMatchObject(
      { position: 4 },
    );
    expect(
      playerReducer(playing, { type: "TICK", position: 99 }),
    ).toMatchObject({ position: 10 });
    const paused = playerReducer(playing, { type: "PAUSE" });
    expect(playerReducer(paused, { type: "TICK", position: 4 })).toBe(paused); // no-op
  });

  it("SEEK works in playing AND paused, clamped both ends", () => {
    const playing = run([{ type: "LOAD" }, { type: "LOADED", duration: 60 }]);
    expect(
      playerReducer(playing, { type: "SEEK", position: 30 }),
    ).toMatchObject({ position: 30 });
    const paused = playerReducer(playing, { type: "PAUSE" });
    expect(playerReducer(paused, { type: "SEEK", position: -3 })).toMatchObject(
      { position: 0 },
    );
    expect(
      playerReducer(paused, { type: "SEEK", position: 999 }),
    ).toMatchObject({ position: 60 });
  });

  it("rate changes persist across pause", () => {
    const playing = run([
      { type: "LOAD" },
      { type: "LOADED", duration: 10 },
      { type: "SET_RATE", rate: 1.5 },
      { type: "PAUSE" },
    ]);
    expect(playing).toMatchObject({ status: "paused", rate: 1.5 });
  });

  it("ENDED lands on paused at the end", () => {
    const state = run([
      { type: "LOAD" },
      { type: "LOADED", duration: 8 },
      { type: "ENDED" },
    ]);
    expect(state).toMatchObject({ status: "paused", position: 8, duration: 8 });
  });

  it("ERROR from any state; LOAD retries from error; RESET → idle", () => {
    const err = run([{ type: "LOAD" }, { type: "ERROR", message: "boom" }]);
    expect(err).toEqual({ status: "error", message: "boom" });
    expect(playerReducer(err, { type: "LOAD" })).toEqual({ status: "loading" });
    expect(playerReducer(err, { type: "RESET" })).toEqual({ status: "idle" });
  });

  it("ignores nonsense transitions", () => {
    expect(playerReducer(initialPlayerState, { type: "PAUSE" })).toBe(
      initialPlayerState,
    );
    expect(
      playerReducer(initialPlayerState, { type: "SEEK", position: 5 }),
    ).toBe(initialPlayerState);
    expect(playerReducer({ status: "loading" }, { type: "LOAD" })).toEqual({
      status: "loading",
    });
  });
});
