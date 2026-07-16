(function initRequestCoordinator(globalScope) {
  function createSingleFlight() {
    const inFlight = new Map();
    const forcedAfterCurrent = new Map();
    let generation = 0;

    function start(key, task, expectedGeneration = generation) {
      if (expectedGeneration !== generation) return Promise.resolve(undefined);
      let pending;
      try {
        pending = Promise.resolve(task());
      } catch (error) {
        pending = Promise.reject(error);
      }
      inFlight.set(key, pending);
      const release = () => {
        if (inFlight.get(key) === pending) inFlight.delete(key);
      };
      pending.then(release, release);
      return pending;
    }

    return {
      run(key, task, { force = false } = {}) {
        const current = inFlight.get(key);
        if (current) {
          if (!force) return current;
          if (forcedAfterCurrent.has(key)) return forcedAfterCurrent.get(key);
          const queuedGeneration = generation;
          const queued = current.catch(() => undefined).then(() => (
            queuedGeneration === generation ? start(key, task, queuedGeneration) : undefined
          ));
          forcedAfterCurrent.set(key, queued);
          const releaseQueued = () => {
            if (forcedAfterCurrent.get(key) === queued) forcedAfterCurrent.delete(key);
          };
          queued.then(releaseQueued, releaseQueued);
          return queued;
        }
        return start(key, task);
      },
      clear(key) {
        generation += 1;
        if (key === undefined) {
          inFlight.clear();
          forcedAfterCurrent.clear();
        } else {
          inFlight.delete(key);
          forcedAfterCurrent.delete(key);
        }
      },
    };
  }

  function createTtlLoader({ ttlMs, now = Date.now }) {
    const cache = new Map();
    const gate = createSingleFlight();
    let generation = 0;
    return {
      run(key, task, { force = false } = {}) {
        const requestGeneration = generation;
        const cached = cache.get(key);
        if (!force && cached && now() - cached.storedAt < ttlMs) {
          return Promise.resolve(cached.value);
        }
        return gate.run(key, async () => {
          const current = cache.get(key);
          if (!force && current && now() - current.storedAt < ttlMs) return current.value;
          const value = await task();
          if (requestGeneration === generation) cache.set(key, { storedAt: now(), value });
          return value;
        }, { force });
      },
      clear(key) {
        generation += 1;
        if (key === undefined) cache.clear();
        else cache.delete(key);
        gate.clear(key);
      },
    };
  }

  const api = { createSingleFlight, createTtlLoader };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalScope.FingerForestRequestCoordinator = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
