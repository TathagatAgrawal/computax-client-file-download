/*
 * Fuzzy search over client IDs and names.
 * Exposed as window.Fuzzy in the browser and via module.exports in Node (for tests).
 *
 * Ranking tiers (higher wins):
 *   ID exact 1000, ID prefix ~900, name/alias matches <= 520, ID substring ~500,
 *   ID subsequence ~300. So typing a full or leading ID always puts that ID first.
 */
(function (root) {
  "use strict";

  function range(start, length) {
    return Array.from({ length }, (_, i) => start + i);
  }

  // In-order subsequence match of q in s (both upper-cased); null if absent.
  function subsequence(q, s) {
    const positions = [];
    let i = 0;
    for (let j = 0; j < s.length && i < q.length; j++) {
      if (s[j] === q[i]) {
        positions.push(j);
        i++;
      }
    }
    if (i < q.length) return null;
    let gaps = 0;
    for (let k = 1; k < positions.length; k++) gaps += positions[k] - positions[k - 1] - 1;
    return { gaps, positions };
  }

  function scoreId(query, id) {
    const q = query.toUpperCase().replace(/\s+/g, "");
    const s = id.toUpperCase();
    if (!q) return null;
    if (s === q) return { score: 1000, positions: range(0, s.length) };
    if (s.startsWith(q)) return { score: 900 - (s.length - q.length), positions: range(0, q.length) };
    const at = s.indexOf(q);
    if (at >= 0) return { score: 500 - at - (s.length - q.length), positions: range(at, q.length) };
    const sub = subsequence(q, s);
    if (sub) return { score: 300 - sub.gaps * 5 - (s.length - q.length), positions: sub.positions };
    return null;
  }

  // Every query word must match some word of the name (any order).
  function scoreName(query, name) {
    const words = query.toUpperCase().split(/\s+/).filter(Boolean);
    if (!words.length || !name) return null;
    const upper = name.toUpperCase();
    const tokens = [...upper.matchAll(/\S+/g)].map((m) => ({ text: m[0], start: m.index }));
    const used = new Set();
    const positions = [];
    let total = 0;
    for (const w of words) {
      let best = null;
      tokens.forEach((t, ti) => {
        let cand = null;
        if (t.text.startsWith(w)) {
          cand = { s: t.text === w ? 120 : 100, pos: range(t.start, w.length) };
        } else {
          const at = t.text.indexOf(w);
          if (at >= 0) {
            cand = { s: 60, pos: range(t.start + at, w.length) };
          } else if (w.length >= 3) {
            const sub = subsequence(w, t.text);
            if (sub && sub.gaps <= w.length) {
              cand = { s: 30 - sub.gaps, pos: sub.positions.map((p) => p + t.start) };
            }
          }
        }
        if (cand && used.has(ti)) cand.s -= 50;
        if (cand && (!best || cand.s > best.s)) best = { ...cand, ti };
      });
      if (!best) return null;
      used.add(best.ti);
      total += best.s;
      positions.push(...best.pos);
    }
    return { score: 400 + total / words.length, positions };
  }

  /*
   * clients: [{id, name, aliases}] already in display order.
   * Returns [{client, score, field: "id"|"name"|"alias", positions, alias?}] best first.
   */
  function search(clients, query) {
    const q = query.trim();
    if (!q) return clients.map((client) => ({ client, score: 0, field: null, positions: [] }));
    const results = [];
    clients.forEach((client, order) => {
      let best = null;
      const consider = (match, field, alias) => {
        if (match && (!best || match.score > best.score)) best = { ...match, field, alias };
      };
      consider(scoreId(q, client.id), "id");
      if (client.name) consider(scoreName(q, client.name), "name");
      for (const alias of client.aliases || []) {
        const m = scoreName(q, alias);
        if (m) m.score -= 10;
        consider(m, "alias", alias);
      }
      if (best) results.push({ client, order, ...best });
    });
    results.sort((a, b) => b.score - a.score || a.order - b.order);
    return results;
  }

  const api = { search, scoreId, scoreName };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Fuzzy = api;
})(typeof window !== "undefined" ? window : globalThis);
