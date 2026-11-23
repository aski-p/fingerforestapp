const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

// www/app.js 의 실제 크리스마스 강제 적용/만료 코드를 시간만 바꿔 돌려 본다.
const source = fs.readFileSync(path.join(__dirname, "../www/app.js"), "utf8");
const code = source.slice(source.indexOf("const xmasForcedKey"), source.indexOf("function showXmasNotice"));

function run(nowIso, store, theme) {
  const ctx = {
    store: { ...store },
    notices: 0,
    Date: class extends Date { static now() { return Date.parse(nowIso); } },
    window: { setTimeout: () => { ctx.notices += 1; } },
  };
  ctx.Date.parse = Date.parse;
  ctx.showXmasNotice = () => {};
  ctx.storeGet = (k) => ctx.store[k] || "";
  ctx.storeSet = (k, v) => { ctx.store[k] = v; };
  vm.createContext(ctx);
  const out = vm.runInContext(`${code}; forceChristmasOnce(${JSON.stringify(theme)})`, ctx);
  return { theme: out, store: ctx.store, notices: ctx.notices };
}

test("12/25 23:59 KST: 아직 크리스마스 유지", () => {
  const r = run("2026-12-25T14:59:00Z", { fruitXmasEdition2026: "applied", fruitXmasPrevTheme: "garden" }, "christmas");
  assert.equal(r.theme, "christmas");
  assert.equal(r.store.fruitXmasEdition2026, "applied");
});

test("12/26 0시 KST: 자동 적용된 기기는 원래 테마로", () => {
  const r = run("2026-12-25T15:00:00Z", { fruitXmasEdition2026: "applied", fruitXmasPrevTheme: "garden" }, "christmas");
  assert.equal(r.theme, "garden");
  assert.equal(r.store.fruitXmasEdition2026, "expired");
});

test("만료 후 처음 여는 기기는 강제 적용하지 않음", () => {
  const r = run("2026-12-27T00:00:00Z", {}, "night");
  assert.equal(r.theme, "night");
  assert.equal(r.notices, 0);
  assert.equal(r.store.fruitXmasEdition2026, undefined);
});

test("직접 다시 고른 크리스마스(restored 후)는 유지", () => {
  const r = run("2026-12-27T00:00:00Z", { fruitXmasEdition2026: "restored", fruitXmasPrevTheme: "garden" }, "christmas");
  assert.equal(r.theme, "christmas");
});

test("이벤트 중 새 기기는 여전히 한 번 강제 적용", () => {
  const r = run("2026-12-10T00:00:00Z", {}, "night");
  assert.equal(r.theme, "christmas");
  assert.equal(r.store.fruitXmasPrevTheme, "night");
});
