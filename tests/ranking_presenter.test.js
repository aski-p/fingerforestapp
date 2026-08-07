const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  giftRankingSummary,
  visibleRankingItems,
} = require("../www/ranking_presenter.js");

const html = fs.readFileSync(path.join(__dirname, "../www/index.html"), "utf8");
assert.ok(
  html.indexOf("/ranking_presenter.js") < html.indexOf("/app.js"),
  "ranking presenter must load before app.js",
);

assert.deepEqual(
  visibleRankingItems("gift", [
    { rank: 1, name: "배성욱", count: 86 },
    { rank: 2, name: "지아연", count: 30 },
    { rank: 3, name: "전수현", count: 30 },
    { rank: 4, name: "박근형", count: 30 },
    { rank: 5, name: "김준", count: 25 },
    { rank: 0, name: "여섯번째", count: 20 },
  ]).map((item) => item.name),
  ["배성욱", "지아연", "전수현", "박근형", "김준"]
);

assert.equal(
  giftRankingSummary({ userName: "박근형", my: { rank: 4, count: 30 } }),
  "박근형님의 열매선물 랭킹은 4등 (열매 30개) 입니다."
);

assert.equal(
  giftRankingSummary({ userName: "박근형", my: { rank: 0, count: 30 } }),
  "박근형님의 열매선물 갯수는 30개 입니다."
);

assert.equal(
  giftRankingSummary({ userName: "박근형", my: { rank: 6, count: 30 } }),
  "박근형님의 열매선물 갯수는 30개 입니다."
);

console.log("ranking presenter tests passed");
