const assert = require("node:assert/strict");
const { createSingleFlight, createTtlLoader } = require("../www/request_coordinator.js");

async function testSingleFlight() {
  let calls = 0;
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const gate = createSingleFlight();
  const task = async () => {
    calls += 1;
    await pending;
    return "done";
  };
  const first = gate.run("refresh", task);
  const second = gate.run("refresh", task);
  assert.equal(calls, 1);
  release();
  assert.deepEqual(await Promise.all([first, second]), ["done", "done"]);
}

async function testTtlLoader() {
  let now = 1000;
  let calls = 0;
  const loader = createTtlLoader({ ttlMs: 300000, now: () => now });
  const task = async () => {
    calls += 1;
    return `value-${calls}`;
  };
  assert.equal(await loader.run("projects", task), "value-1");
  assert.equal(await loader.run("projects", task), "value-1");
  assert.equal(calls, 1);
  now += 300001;
  assert.equal(await loader.run("projects", task), "value-2");
  assert.equal(await loader.run("projects", task, { force: true }), "value-3");
  assert.equal(calls, 3);
}

async function testSingleFlightRejectionReleasesKey() {
  const gate = createSingleFlight();
  await assert.rejects(gate.run("refresh", async () => {
    throw new Error("expected failure");
  }), /expected failure/);
  assert.equal(await gate.run("refresh", async () => "recovered"), "recovered");
}

async function testForcedSingleFlightRunsAfterCurrentRequest() {
  let release;
  let calls = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  const gate = createSingleFlight();
  const first = gate.run("refresh", async () => {
    calls += 1;
    await pending;
    return "old";
  });
  const forced = gate.run("refresh", async () => {
    calls += 1;
    return "new";
  }, { force: true });
  assert.equal(calls, 1);
  release();
  assert.deepEqual(await Promise.all([first, forced]), ["old", "new"]);
  assert.equal(calls, 2);
}

async function testForcedTtlLoadRunsAfterCurrentRequest() {
  let release;
  let calls = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  const loader = createTtlLoader({ ttlMs: 300000 });
  const first = loader.run("projects", async () => {
    calls += 1;
    await pending;
    return "old";
  });
  const forced = loader.run("projects", async () => {
    calls += 1;
    return "new";
  }, { force: true });
  assert.equal(calls, 1);
  release();
  assert.deepEqual(await Promise.all([first, forced]), ["old", "new"]);
  assert.equal(calls, 2);
  assert.equal(await loader.run("projects", async () => "unexpected"), "new");
}

async function testClearInvalidatesActiveTtlLoad() {
  let release;
  let calls = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  const loader = createTtlLoader({ ttlMs: 300000 });
  const first = loader.run("projects", async () => {
    calls += 1;
    await pending;
    return "pre-logout";
  });
  loader.clear();
  release();
  assert.equal(await first, "pre-logout");
  assert.equal(await loader.run("projects", async () => {
    calls += 1;
    return "post-logout";
  }), "post-logout");
  assert.equal(calls, 2);
}

async function testClearCancelsQueuedForcedTask() {
  let release;
  let calls = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  const gate = createSingleFlight();
  const first = gate.run("refresh", async () => {
    calls += 1;
    await pending;
    return "old";
  });
  const forced = gate.run("refresh", async () => {
    calls += 1;
    return "must-not-run";
  }, { force: true });
  gate.clear();
  release();
  assert.equal(await first, "old");
  assert.equal(await forced, undefined);
  assert.equal(calls, 1);
}

(async () => {
  await testSingleFlight();
  await testTtlLoader();
  await testSingleFlightRejectionReleasesKey();
  await testForcedSingleFlightRunsAfterCurrentRequest();
  await testForcedTtlLoadRunsAfterCurrentRequest();
  await testClearInvalidatesActiveTtlLoad();
  await testClearCancelsQueuedForcedTask();
  console.log("request coordinator tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
