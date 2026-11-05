// Tests for static/fuzzy.js. Run with: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { search } = require("../src/computax_client_file_download/static/fuzzy.js");

const clients = [
  { id: "1", name: "ASHA SHARMA", aliases: ["ASHA VERMA"] },
  { id: "42", name: "SHARMA TRADERS", aliases: [] },
  { id: "103B", name: "MOHAN LAL", aliases: [] },
  { id: "109B", name: "RAKESH SHARMA", aliases: [] },
  { id: "109B1", name: "PRIYA SHARMA", aliases: [] },
  { id: "NEHA4", name: null, aliases: [] },
  { id: "NEHA5", name: "NEHA GUPTA", aliases: [] },
];

const top = (q) => search(clients, q).map((r) => r.client.id);

test("exact ID ranks first", () => {
  assert.equal(top("42")[0], "42");
  assert.deepEqual(top("109b").slice(0, 2), ["109B", "109B1"]);
});

test("ID prefix beats name matches", () => {
  assert.deepEqual(top("neha").slice(0, 2), ["NEHA4", "NEHA5"]);
});

test("name search is word-order independent", () => {
  assert.equal(top("sharma rak")[0], "109B");
  assert.equal(top("rakesh sh")[0], "109B");
});

test("all name matches are returned", () => {
  assert.deepEqual(new Set(top("sharma")), new Set(["1", "42", "109B", "109B1"]));
});

test("old names match as aliases", () => {
  const [hit] = search(clients, "verma");
  assert.equal(hit.client.id, "1");
  assert.equal(hit.field, "alias");
});

test("typos with missing letters still match names", () => {
  assert.equal(top("rakesh shrma")[0], "109B");
});

test("non-matching query returns nothing", () => {
  assert.deepEqual(top("zzzz"), []);
});

test("empty query returns everyone in order", () => {
  assert.deepEqual(top(""), clients.map((c) => c.id));
});
