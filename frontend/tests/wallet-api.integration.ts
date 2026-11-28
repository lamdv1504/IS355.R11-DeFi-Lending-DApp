import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Wallet, getBytes } from "ethers";
import { WalletClient, type Eip1193Provider } from "../src/lib/wallet-client.ts";
import { retrieveDocument, type HubConnection } from "../src/lib/ipfs-hub.ts";
import type { DeploymentRegistry } from "../src/lib/wallet-transactions.ts";
const context = JSON.parse(process.env.L05_TEST_CONTEXT || "{}") as {base:string;test_key:string;contracts:Record<string,{address:string}>};
assert.ok(context.base && context.test_key);
const signer=new Wallet(context.test_key.startsWith("0x")?context.test_key:"0x"+context.test_key);
const registry=JSON.parse(readFileSync(new URL("../src/config/contracts.json",import.meta.url),"utf8")) as DeploymentRegistry;
registry.networks.local.contracts=context.contracts;
const checks:string[]=[];
let broadcasts=0;
const provider:Eip1193Provider={async request({method,params}) {
  switch(method) {
    case "eth_accounts":case "eth_requestAccounts":return [signer.address];
    case "eth_chainId":return "0x7a69";
    case "personal_sign":return signer.signMessage(getBytes((params as string[])[0]));
    case "eth_sendTransaction": {
      broadcasts++;const response=await fetch(context.base+"/__l05_test__/broadcast",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify((params as unknown[])[0])});
      assert.equal(response.status,200);return (await response.json()).hash;
    }
    case "eth_getTransactionReceipt":return (await fetch(context.base+"/__l05_test__/receipt/"+(params as string[])[0])).json();
    default:throw new Error("Unexpected RPC "+method);
  }
}};
const client=new WalletClient({registry,getProvider:()=>provider,domain:()=>"localhost",baseUrl:context.base,pause:async()=>{},receiptAttempts:2});
await client.connect();await client.authenticate();
assert.ok(client.getSnapshot().session?.token);assert.deepEqual(client.getSnapshot().session?.roles,["BORROWER"]);
checks.push("real Q05 nonce/signature/verify establishes wallet-bound session");
const deposit={action:"DEPOSIT_LENDER" as const,args:{amount_wad:(10n*10n**18n).toString()}};
await client.prepare(deposit);assert.equal(client.getSnapshot().quote?.approvalRequired,true);assert.equal(broadcasts,0);
checks.push("prepare discovers missing allowance without broadcasting");
await client.prepareApproval();await client.send();assert.equal(client.getSnapshot().records.at(-1)?.status,"confirmed");
checks.push("approve exact Pool/amount is signed and checked by Q05 confirm");
await client.prepare(deposit);assert.equal(client.getSnapshot().quote?.approvalRequired,false);await client.send();
assert.equal(client.getSnapshot().records.at(-1)?.status,"confirmed");assert.equal(broadcasts,2);
checks.push("fresh deposit quote passes canonical calldata/gas validation and confirms");
await client.prepare({action:"BORROW",args:{amount_wad:(50n*10n**18n).toString()},assetDescription:"L05 isolated integration test collateral"});
const cid=client.getSnapshot().quote?.cid;assert.ok(cid);assert.equal(broadcasts,2);
checks.push("real Q03 creates encrypted PDF/CID before borrow is signed");
await client.send();assert.equal(client.getSnapshot().records.at(-1)?.status,"confirmed");
assert.equal(client.getSnapshot().records.at(-1)?.cid,cid);
checks.push("Q05 verifies LoanBorrowed event and persists Q03 CID/tx binding");
const connection:HubConnection={mode:"api",baseUrl:context.base,token:client.getSnapshot().session!.token,network:"local"};
const pdf=await retrieveDocument(connection,cid!);assert.equal(new TextDecoder().decode(pdf.bytes.slice(0,5)),"%PDF-");assert.equal(pdf.verification,"browser");
checks.push("same signed session retrieves/decrypts owner PDF and browser verifies SHA-256");
const guest=await fetch(context.base+"/api/ipfs/documents/"+cid+"/retrieve?network=local");assert.equal(guest.status,401);
checks.push("private PDF stays protected from unauthenticated retrieval");
const pool=await client.json("/api/pool");assert.equal(pool.chain_id,31337);
checks.push("post-confirm refresh reads selected local network metadata");
assert.equal(broadcasts,3);
client.dispose();
console.log(JSON.stringify({scope:"Real Q05 HTTP/auth/PDF/confirm; ephemeral test signer and RPC/receipt doubles; no extension or chain broadcast",checks,broadcasts}));
