(function initSocialFeed(globalScope) {
  // 대화방 메시지 목록: 겹쳐서 도착한 응답(4초 폴링 + 전송 직후 조회)이 같은 메시지를 두 번 그리지 않게 한다.
  function createMessageFeed() {
    let roomId = null;
    let lastId = 0;
    let seen = new Set();
    return {
      open(nextRoomId) {
        roomId = nextRoomId;
        lastId = 0;
        seen = new Set();
      },
      get roomId() { return roomId; },
      get lastId() { return lastId; },
      // 요청을 보낸 방(requestRoomId)이 지금 방과 다르면 버리고, 아직 그리지 않은 메시지만 돌려준다.
      accept(requestRoomId, items) {
        if (requestRoomId !== roomId) return [];
        const fresh = [];
        for (const item of items || []) {
          const id = Number(item && item.id);
          if (!Number.isFinite(id) || seen.has(id)) continue;
          seen.add(id);
          if (id > lastId) lastId = id;
          fresh.push(item);
        }
        return fresh;
      },
    };
  }

  // 한 번에 하나만 보내기: 전송 중 다시 눌러도(더블 탭·엔터+버튼) 두 번째는 무시한다.
  function createSendGate() {
    let busy = false;
    return {
      get busy() { return busy; },
      async run(task) {
        if (busy) return false;
        busy = true;
        try {
          await task();
          return true;
        } finally {
          busy = false;
        }
      },
    };
  }

  const api = { createMessageFeed, createSendGate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  globalScope.FingerForestSocialFeed = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
