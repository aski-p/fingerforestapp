const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createMessageFeed, createSendGate } = require("../www/social_feed.js");

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function testFeedDropsMessagesAlreadyShown() {
  const feed = createMessageFeed();
  feed.open(7);
  assert.deepEqual(feed.accept(7, [{ id: 1 }, { id: 2 }]).map((m) => m.id), [1, 2]);
  // 폴링과 전송 직후 조회가 같은 after 값으로 같은 메시지를 다시 가져온 경우
  assert.deepEqual(feed.accept(7, [{ id: 2 }, { id: 3 }]).map((m) => m.id), [3]);
  assert.deepEqual(feed.accept(7, [{ id: 3 }]), []);
  assert.equal(feed.lastId, 3);
  // 다른 방에서 보낸 요청의 늦은 응답은 버린다
  assert.deepEqual(feed.accept(8, [{ id: 9 }]), []);
  feed.open(8);
  assert.equal(feed.lastId, 0);
  assert.deepEqual(feed.accept(8, [{ id: 2 }]).map((m) => m.id), [2]);
}

async function testSendGateRunsOneAtATime() {
  const gate = createSendGate();
  let calls = 0;
  let release;
  const first = gate.run(() => { calls += 1; return new Promise((resolve) => { release = resolve; }); });
  assert.equal(gate.busy, true);
  assert.equal(await gate.run(() => { calls += 1; }), false);
  release();
  assert.equal(await first, true);
  assert.equal(gate.busy, false);
  await assert.rejects(gate.run(() => { throw new Error("boom"); }));
  assert.equal(gate.busy, false);
  assert.equal(calls, 1);
}

// www/app.js 의 실제 대화방 코드를 가짜 화면·가짜 서버에 올려 "보내면 두 번 보임"을 재현한다.
function loadRoomCode({ sendMs, listMs }) {
  const source = fs.readFileSync(path.join(__dirname, "../www/app.js"), "utf8");
  const slice = (from, to) => source.slice(source.indexOf(from), source.indexOf(to));
  const elements = {};
  const el = (id) => {
    if (!elements[id]) {
      elements[id] = {
        value: "", html: [], listeners: {}, textContent: "",
        classList: { contains: () => false },
        set innerHTML(value) { this.html = value ? [value] : []; },
        get innerHTML() { return this.html.join(""); },
        insertAdjacentHTML(_position, html) { this.html.push(html); },
        querySelector: () => null,
        addEventListener(type, handler) { this.listeners[type] = handler; },
      };
    }
    return elements[id];
  };
  const server = { rows: [], sendCalls: 0, payloads: [] };
  let nextRandom = 0;
  const context = {
    $: el, document: { hidden: false }, console,
    window: { setInterval, clearInterval, FingerForestSocialFeed: { createMessageFeed, createSendGate } },
    escapeHtml: (value) => String(value), socialTimeLabel: () => "", toast: () => {}, showSocialView: () => {},
    randomId: () => `client-${(nextRandom += 1)}`,
    api: async (url, payload) => {
      if (url === "/api/social/send") {
        server.sendCalls += 1;
        server.payloads.push(payload);
        await delay(sendMs);
        server.rows.push({ id: server.rows.length + 1, room: payload.room, body: payload.body, mine: true, at: "" });
        return { id: server.rows.length };
      }
      if (url.startsWith("/api/social/messages")) {
        const query = new URLSearchParams(url.split("?")[1]);
        const snapshot = server.rows.filter((m) => m.room === Number(query.get("room")) && m.id > Number(query.get("after")));
        await delay(listMs);
        return { items: snapshot };
      }
      return {};
    },
  };
  vm.createContext(context);
  vm.runInContext(
    'const social = { roomId: null, lastId: 0, roomTimer: null };\n'
    + 'const socialFeed = window.FingerForestSocialFeed.createMessageFeed();\n'
    + 'const socialSendGate = window.FingerForestSocialFeed.createSendGate();\n'
    + slice("function renderSocialMessages", "async function refreshSocialNotes")
    + slice('$("socialSendForm").addEventListener', '$("socialInput").addEventListener')
    + "\nglobalThis.room = { openSocialRoom, loadSocialMessages, stopRoomPolling, social };",
    context,
  );
  const bubbles = (text) => el("socialMessages").innerHTML.split(`<span>${text}</span>`).length - 1;
  const submit = () => el("socialSendForm").listeners.submit({ preventDefault() {} });
  return { room: context.room, el, server, bubbles, submit };
}

async function testPollOverlappingSendShowsMessageOnce() {
  const { room, el, server, bubbles, submit } = loadRoomCode({ sendMs: 20, listMs: 60 });
  await room.openSocialRoom(1, "방");
  room.stopRoomPolling();
  el("socialInput").value = "안녕";
  const sending = submit();
  await delay(40); // 서버에는 저장됐고, 전송 직후 조회가 진행 중일 때
  const poll = room.loadSocialMessages(false); // 4초 폴링이 같은 after 값으로 겹쳐 들어온다
  await Promise.all([sending, poll]);
  assert.equal(server.sendCalls, 1);
  assert.equal(server.rows.length, 1);
  assert.equal(bubbles("안녕"), 1, "보낸 메시지는 화면에 한 번만 보여야 한다");
  assert.equal(room.social.lastId, 1);
}

async function testDoubleSubmitSendsOnceWithClientId() {
  const { room, el, server, bubbles, submit } = loadRoomCode({ sendMs: 30, listMs: 5 });
  await room.openSocialRoom(1, "방");
  room.stopRoomPolling();
  el("socialInput").value = "점심?";
  const first = submit();
  el("socialInput").value = "점심?"; // 전송 중에 같은 글이 다시 들어와 또 눌린 경우(연타·IME 재입력)
  const second = submit();
  await Promise.all([first, second]);
  assert.equal(server.sendCalls, 1);
  assert.equal(bubbles("점심?"), 1);
  assert.match(server.payloads[0].clientId, /^client-\d+$/);
}

async function testLateResponseFromPreviousRoomIsDropped() {
  const { room, el, server } = loadRoomCode({ sendMs: 5, listMs: 40 });
  server.rows.push({ id: 1, room: 1, body: "방1 글", mine: false, at: "" });
  const openingFirst = room.openSocialRoom(1, "방1");
  await delay(10);
  const openingSecond = room.openSocialRoom(2, "방2");
  await Promise.all([openingFirst, openingSecond]);
  room.stopRoomPolling();
  assert.equal(el("socialMessages").innerHTML.includes("방1 글"), false);
}

function testPageLoadsFeedBeforeApp() {
  const html = fs.readFileSync(path.join(__dirname, "../www/index.html"), "utf8");
  assert.ok(html.indexOf('src="/social_feed.js?v=') > 0);
  assert.ok(html.indexOf('src="/social_feed.js?v=') < html.indexOf('src="/app.js?v='));
}

(async () => {
  testFeedDropsMessagesAlreadyShown();
  await testSendGateRunsOneAtATime();
  await testPollOverlappingSendShowsMessageOnce();
  await testDoubleSubmitSendsOnceWithClientId();
  await testLateResponseFromPreviousRoomIsDropped();
  testPageLoadsFeedBeforeApp();
  console.log("social feed tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
