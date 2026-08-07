(function initRankingPresenter(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.RankingPresenter = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function rankingPresenterFactory() {
  function numberText(value) {
    return Number(value || 0).toLocaleString("ko-KR");
  }

  function visibleRankingItems(kind, items) {
    const rows = Array.isArray(items) ? items : [];
    return kind === "gift" ? rows.slice(0, 5) : rows;
  }

  function giftRankingSummary(data) {
    const my = (data && data.my) || {};
    const name = (data && data.userName) || my.name || "사용자";
    const rank = Number(my.rank || 0);
    const count = numberText(my.count);
    if (rank >= 1 && rank <= 5) {
      return `${name}님의 열매선물 랭킹은 ${numberText(rank)}등 (열매 ${count}개) 입니다.`;
    }
    return `${name}님의 열매선물 갯수는 ${count}개 입니다.`;
  }

  return {
    giftRankingSummary,
    visibleRankingItems,
  };
});
