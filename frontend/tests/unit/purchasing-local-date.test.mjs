import test from "node:test";
import assert from "node:assert/strict";

import { toLocalDateInputValue } from "../../src/features/purchasing/dateInput.js";

test("supplier invoice date uses the Indian local calendar date after midnight", () => {
  const previousTimezone = process.env.TZ;
  process.env.TZ = "Asia/Kolkata";
  try {
    const now = new Date("2026-11-09T19:00:00.000Z"); // 00:30 on 10 November in India
    assert.equal(toLocalDateInputValue(now), "2026-11-10");
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = previousTimezone;
  }
});
