import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { creditReportView, apiBase, apiRequest, assertHash, auditEntries, decodeDocument, errorMessage, HubError, listDocuments, normalizeCid, parseMetadata, ratesChartData, retrieveDocument, retrieveSample, safeFilename, sha256, walletChartData, type HubConnection } from "../src/lib/ipfs-hub.ts";

const samples = JSON.parse(readFileSync(new URL("../src/data/l04-samples.json", import.meta.url), "utf8"));
const documents = samples.documents.map(parseMetadata);
const audit = documents.find((d: { document_type: string }) => d.document_type === "AUDIT_LOGS")!;
const connection: HubConnection = { mode: "api", baseUrl: "http://127.0.0.1:8000", token: "verified-session" };
const bytes = new Uint8Array(readFileSync(new URL("../public/l04/audit_logs_sample.json", import.meta.url)));

test("CID input accepts raw CID, ipfs URI and direct gateway link", () => {
  for (const input of [audit.cid, "ipfs://" + audit.cid, "https://example.org/ipfs/" + audit.cid]) assert.equal(normalizeCid(input), audit.cid);
  assert.equal(normalizeCid("QmYwAPJzv5CZsnAzt8auVTLjCdSYNQh47jH3PtGp4C1sxk").length, 46);
});
test("CID input rejects traversal, arbitrary URL, malformed multihash and subpath", () => {
  for (const input of ["", "../secret", "bafy...", "https://example.org/file", audit.cid + "/secret", "ipfs://" + audit.cid + "?role=ADMIN", "b" + "a".repeat(58)]) assert.throws(() => normalizeCid(input));
});
test("API origin prevents token transmission over remote HTTP or credentials in URL", () => {
  assert.equal(apiBase("https://api.example.org/"), "https://api.example.org");
  for (const url of ["http://api.example.org", "https://user:pass@example.org", "https://example.org/api", "https://example.org/?token=x", "file:///api"]) assert.throws(() => apiBase(url));
});
test("public sample hash matches H03 original bytes", async () => {
  await assertHash(bytes, audit.plaintext_sha256);
  const source = new Uint8Array(readFileSync(new URL("../../ipfs_storage/samples/audit_logs_sample.json", import.meta.url)));
  assert.deepEqual(bytes, source);
});
test("tampered public sample cannot be previewed or downloaded", async () => {
  const altered = Uint8Array.from(bytes); altered[10] ^= 1;
  await assert.rejects(retrieveSample(audit.cid, documents, undefined, async () => new Response(altered)), (e: unknown) => e instanceof HubError && e.status === 409);
});
test("private sample retrieval denies before fetching any plaintext", async () => {
  for (const doc of documents.filter((d: { visibility: string }) => d.visibility === "PRIVATE")) {
    let called = false;
    await assert.rejects(retrieveSample(doc.cid, documents, undefined, async () => { called = true; return new Response("private"); }), (e: unknown) => e instanceof HubError && e.status === 401);
    assert.equal(called, false);
  }
});
test("frontend only distributes private ciphertext with its recorded H03 hash", async () => {
  for (const doc of documents.filter((d: { visibility: string }) => d.visibility === "PRIVATE")) {
    const filename = doc.document_type === "LOAN_AGREEMENT" ? "loan_agreement" : "credit_report";
    const payload = new Uint8Array(readFileSync(new URL("../public/l04/" + filename + "_sample.encrypted.json", import.meta.url)));
    await assertHash(payload, doc.ciphertext_sha256);
    const envelope = JSON.parse(new TextDecoder().decode(payload));
    assert.ok(envelope.ciphertext_b64);
    assert.equal(envelope.master_key, undefined);
    assert.equal(envelope.plaintext, undefined);
  }
});
test("private metadata cannot be mislabeled as public or unencrypted", () => {
  assert.throws(() => parseMetadata({ ...documents[0], visibility: "PUBLIC" }));
  assert.throws(() => parseMetadata({ ...documents[0], encrypted: false }));
});
test("API sends bearer session but no client role/wallet proof", async () => {
  await listDocuments(connection, undefined, async (url, options) => {
    assert.equal(url, connection.baseUrl + "/api/ipfs/documents");
    const headers = new Headers(options?.headers);
    assert.equal(headers.get("Authorization"), "Bearer verified-session");
    assert.equal(headers.get("X-Role"), null);
    assert.equal(options?.cache, "no-store"); assert.equal(options?.redirect, "error");
    return Response.json({ documents: [audit] });
  });
});
for (const status of [401, 403, 404, 503]) test("HTTP " + status + " remains an error without local sample fallback", async () => {
  let calls = 0;
  await assert.rejects(retrieveDocument(connection, audit.cid, audit, undefined, async () => { calls++; return Response.json({ detail: "denied" }, { status }); }), (e: unknown) => e instanceof HubError && e.status === status);
  assert.equal(calls, 1);
});
test("guest API calls carry no fabricated authorization", async () => {
  await apiRequest({ ...connection, token: "" }, "/api/ipfs/documents", {}, async (_url, options) => {
    assert.equal(new Headers(options?.headers).get("Authorization"), null); return Response.json({ documents: [] });
  });
});
test("PDF uses original plaintext SHA-256 and blocks tampering", async () => {
  const pdf = new TextEncoder().encode("%PDF-1.4\noriginal");
  const hash = await sha256(pdf);
  const meta = { ...documents[0], plaintext_sha256: hash };
  const doc = await decodeDocument(new Response(pdf, { headers: { "Content-Type": "application/pdf" } }), meta.cid, meta);
  assert.equal(doc.verification, "browser"); assert.equal(doc.downloadSha256, hash);
  await assert.rejects(decodeDocument(new Response("different", { headers: { "Content-Type": "application/pdf" } }), meta.cid, meta));
});
test("JSON wrapper preserves original hash and distinguishes serialized download hash", async () => {
  const content = { document_type: "AUDIT_LOGS", entries: [] };
  const originalHash = "a".repeat(64);
  const doc = await decodeDocument(Response.json({ cid: audit.cid, sha256: originalHash, content }), audit.cid, { ...audit, plaintext_sha256: originalHash });
  assert.equal(doc.verification, "backend"); assert.equal(doc.sourceSha256, originalHash);
  assert.equal(doc.downloadSha256, await sha256(doc.bytes)); assert.notEqual(doc.downloadSha256, originalHash);
});
test("JSON wrapper CID and hash mismatches are blocked", async () => {
  await assert.rejects(decodeDocument(Response.json({ cid: documents[0].cid, sha256: audit.plaintext_sha256, content: {} }), audit.cid, audit));
  await assert.rejects(decodeDocument(Response.json({ cid: audit.cid, sha256: "b".repeat(64), content: {} }), audit.cid, audit));
});
test("mixed source rate history is not connected as one observed history", () => {
  const rows = auditEntries(samples.audit).slice(0, 2);
  rows[1] = { ...rows[1], data_kind: "ON_CHAIN" };
  const points = ratesChartData(rows);
  assert.equal(points[0].chainBorrow, null); assert.equal(points[1].sampleBorrow, null);
  assert.equal(points[1].chainBorrow, rows[1].borrow_apy_percent);
});
test("audit validation rejects duplicate months and unknown provenance", () => {
  const row = auditEntries(samples.audit)[0];
  assert.throws(() => auditEntries({ entries: [row, row] }));
  assert.throws(() => auditEntries({ entries: [{ ...row, data_kind: "FAKE" }] }));
});
test("wallet bars preserve WAD strings without treating debt as assets", () => {
  const input = { myusdt: "1500000000000000000000", collateral: "1000000000000000000000", debt: "500000000000000000000", interest: "123456789123456789" };
  const rows = walletChartData(input);
  assert.equal(rows.length, 4); assert.equal(rows[2].amount, 500); assert.equal(rows[3].wad, input.interest);
  assert.throws(() => walletChartData({ ...input, debt: "-1" }));
  assert.throws(() => walletChartData({ ...input, interest: undefined as unknown as string }));
});
test("download filenames cannot escape paths and access errors use required Vietnamese wording", () => {
  assert.equal(safeFilename("../../private/report.json").includes("/"), false);
  assert.ok(errorMessage(new HubError(403, "x")).includes("Không có quyền truy cập"));
  assert.ok(errorMessage(new HubError(401, "x")).includes("ký xác thực ví"));
});

test("credit report reads the nested Q04 score, summary and repayment history", () => {
  const content = JSON.parse(readFileSync(new URL("../../ipfs_storage/samples/credit_report_sample.json", import.meta.url), "utf8"));
  const view = creditReportView(content);
  assert.equal(view.score, 760); assert.equal(view.summary.total_loans, 2);
  assert.equal(view.loans[0].status, "REPAID_ON_TIME");
  assert.throws(() => creditReportView({ ...content, credit_score: 760 }));
  assert.throws(() => creditReportView({ ...content, credit_score: { score: 999 } }));
});
