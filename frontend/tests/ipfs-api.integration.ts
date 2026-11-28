/** Executed by scripts/verify_l04_frontend_api.py against the actual Q05 FastAPI app. */
import assert from "node:assert/strict";
import { listDocuments, retrieveDocument, HubError, auditEntries, sha256, type HubConnection } from "../src/lib/ipfs-hub.ts";
const context = JSON.parse(process.env.L04_TEST_CONTEXT || "{}");
const connection = (role: string): HubConnection => ({ mode: "api", baseUrl: context.base_url, token: context.tokens[role] || "" });
const evidence: Record<string, unknown>[] = [];
for (const role of ["guest", "lender", "other", "owner", "admin"]) {
  const items = await listDocuments(connection(role));
  for (const type of ["pdf", "credit"]) {
    const metadata = context.documents[type];
    const expected = role === "guest" ? 401 : ["lender", "other"].includes(role) ? 403 : 200;
    try {
      const doc = await retrieveDocument(connection(role), metadata.cid, metadata);
      assert.equal(expected, 200);
      assert.equal(await sha256(doc.bytes), doc.downloadSha256);
      if (type === "pdf") assert.match(new TextDecoder().decode(doc.bytes.slice(0, 8)), /^%PDF-/);
      else assert.equal(doc.json?.document_type, "CREDIT_REPORT");
    } catch (error) {
      if (!(error instanceof HubError)) throw error;
      assert.equal(error.status, expected);
    }
    assert.equal(items.some((d) => d.cid === metadata.cid), expected === 200);
    evidence.push({ role, document: type, http: expected });
  }
  for (const type of ["audit_json", "audit_csv"]) {
    const doc = await retrieveDocument(connection(role), context.documents[type].cid, context.documents[type]);
    if (type === "audit_json") assert.ok(auditEntries(doc.json).length);
    else assert.equal(doc.verification, "browser");
    evidence.push({ role, document: type, http: 200 });
  }
}
console.log(JSON.stringify({ service: "Q05 FastAPI + actual H03/Q03/Q04 local encrypted storage", blockchain: "test double; no live RPC", scenarios: evidence.length, results: evidence }, null, 2));
