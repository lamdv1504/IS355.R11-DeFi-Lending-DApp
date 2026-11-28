import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Interface, Wallet, getBytes, toUtf8String } from "ethers";
import { WalletClient, walletError, type Eip1193Provider } from "../src/lib/wallet-client.ts";
import { validatePrepared, type DeploymentRegistry, type Operation } from "../src/lib/wallet-transactions.ts";
import { walletRegistry } from "../src/lib/wallet-registry.ts";

const registry = JSON.parse(readFileSync(new URL("../src/config/contracts.json", import.meta.url), "utf8")) as DeploymentRegistry;
const WAD = 10n ** 18n;
const CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3pte3b5fmd2xps3fqqfi2uvqa";
const HASH = "0x" + "ab".repeat(32);
const account = Wallet.createRandom();
const other = Wallet.createRandom();
const deployed = (name: string) => registry.networks.local.contracts[name].address;
const abi = (name: string) => new Interface(registry.contracts[name].abi!);
const deposit: Operation = { action: "DEPOSIT_LENDER", args: { amount_wad: (10n * WAD).toString() } };
function quote(op: Operation, allowance = 1000n * WAD) {
  let name = "LendingPool", data: string;
  const args = op.args;
  switch (op.action) {
    case "DEPOSIT_LENDER": data = abi(name).encodeFunctionData("depositLender", [args.amount_wad]); break;
    case "APPROVE_MYUSDT": name = "MyUSDT"; data = abi(name).encodeFunctionData("approve", [deployed("LendingPool"), args.amount_wad]); break;
    case "APPROVE_COLLATERAL_NFT": name = "CollateralNFT"; data = abi(name).encodeFunctionData("approve", [deployed("LendingPool"), args.token_id]); break;
    case "DEPOSIT_COLLATERAL": data = abi(name).encodeFunctionData("depositCollateral", [args.collateral_amount_or_token_id, args.is_nft]); break;
    case "BORROW": data = abi(name).encodeFunctionData("borrow", [args.amount_wad, args.agreement_cid]); break;
    case "FAUCET_MYUSDT": name = "MyUSDT"; data = abi(name).encodeFunctionData("faucet", [args.recipient_address || account.address, args.amount_wad]); break;
    case "MOCK_ORACLE_MULTIPLIER": name = "PriceOracle"; data = abi(name).encodeFunctionData("setPriceMultiplierBps", [args.multiplier_bps]); break;
    default: throw new Error("Unsupported test fixture action");
  }
  const isNft = op.action === "DEPOSIT_COLLATERAL" && args.is_nft;
  const isToken = op.action === "DEPOSIT_LENDER" || (op.action === "DEPOSIT_COLLATERAL" && !args.is_nft);
  const amount = BigInt(String(args.amount_wad || args.collateral_amount_or_token_id || 0));
  const approval = !!isNft || (isToken && allowance < amount);
  return {
    intent_id: "intent-" + op.action, signing: "client_wallet",
    unsignedTransaction: { from: account.address, to: deployed(name), data, chainId: 31337, value: 0, gasPrice: "1000000000", ...(approval ? {} : { gas: 120000 }) },
    context: { network: "local", chain_id: 31337, account: account.address, action: op.action, block_number: 10 },
    availability: { ready: true, missing_contracts: [] },
    allowance: { token_address: isNft ? deployed("CollateralNFT") : isToken ? deployed("MyUSDT") : null, spender_address: isNft || isToken ? deployed("LendingPool") : null,
      amount_wad: isToken ? amount.toString() : null, current_allowance_wad: isToken ? allowance.toString() : null, approval_required: approval, ...(isNft ? { token_id: Number(args.collateral_amount_or_token_id) } : {}) },
    gas_quote: { estimation_status: approval ? "PENDING_APPROVAL" : "ESTIMATED", gas_price_wei: "1000000000", estimated_gas: approval ? null : 100000,
      gas_limit: approval ? null : 120000, estimated_fee_wei: approval ? null : "100000000000000", max_fee_wei: approval ? null : "120000000000000" },
    interest_quote: null, preview: {},
  };
}
class Provider implements Eip1193Provider {
  account = account.address; chain = "0x7a69"; signedBy = account;
  requests: {method: string; params?: unknown[] | Record<string, unknown>}[] = [];
  events = new Map<string, (value: unknown) => void>();
  receipt: unknown = { transactionHash: HASH, status: "0x1", blockNumber: "0xb" };
  rejectSend: unknown = null;
  async request(args: {method: string; params?: unknown[] | Record<string, unknown>}) {
    this.requests.push(args);
    switch (args.method) {
      case "eth_accounts": case "eth_requestAccounts": return [this.account];
      case "eth_chainId": return this.chain;
      case "personal_sign": return this.signedBy.signMessage(getBytes((args.params as string[])[0]));
      case "eth_sendTransaction": if (this.rejectSend) throw this.rejectSend; return HASH;
      case "eth_getTransactionReceipt": return this.receipt;
      case "wallet_switchEthereumChain": this.chain = (args.params as {chainId:string}[])[0].chainId; this.events.get("chainChanged")?.(this.chain); return null;
      default: throw new Error("Unexpected RPC " + args.method);
    }
  }
  on(event: string, listener: (v:unknown)=>void) { this.events.set(event, listener); }
  removeListener(event: string) { this.events.delete(event); }
  emitAccount(value: string) { this.account=value; this.events.get("accountsChanged")?.([value]); }
}
function harness() {
  const provider = new Provider();
  let now = Date.now(), allowance = 1000n * WAD, mismatch = false, failConfirm = false;
  const calls: {path:string; body:Record<string,unknown>; auth:string|null}[] = [];
  let mutate: ((body: ReturnType<typeof quote>)=>void) | undefined;
  let holdPdf: Promise<void> | null = null;
  let prepared: Operation = deposit;
  const message = "IS355 wallet session\nNonce: random-test-nonce\nChain: 31337";
  const fetcher: typeof fetch = async (input, init) => {
    const url = new URL(String(input)), body = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
    const headers = new Headers(init?.headers);
    calls.push({path:url.pathname,body,auth:headers.get("Authorization")});
    let payload: unknown;
    switch (url.pathname) {
      case "/api/auth/nonce": payload = {wallet_address:provider.account,chain_id:Number(BigInt(provider.chain)),domain:"localhost",nonce:"random-test-nonce",message,expires_at:Math.floor(now/1000)+60}; break;
      case "/api/auth/verify": payload = {wallet_address:provider.account,chain_id:Number(BigInt(provider.chain)),access_token:"opaque-test-session",token_type:"bearer",roles:["BORROWER","ADMIN"],expires_at:Math.floor(now/1000)+3600}; break;
      case "/api/ipfs/create-agreement": if (holdPdf) await holdPdf; payload = {cid:CID,status:"PRE_BORROW_UNSIGNED",tx_hash:null}; break;
      case "/api/transactions/prepare": {
        prepared = { action: body.action as Operation["action"], args: body.args as Operation["args"] };
        const data = quote(prepared,allowance); mutate?.(data); payload=data; break;
      }
      case "/api/transactions/confirm":
        if(failConfirm) return new Response(JSON.stringify({detail:"Backend unavailable"}),{status:503});
        if(prepared.action === "APPROVE_MYUSDT") allowance = BigInt(String(prepared.args.amount_wad));
        payload = {tx_hash:HASH,status:1,block_number:11,loan_binding:prepared.action === "BORROW" ? {
          agreement_cid:mismatch?"wrong-cid":CID, borrower_wallet:account.address,network:"local",chain_id:31337,tx_hash:HASH,principal_wad:prepared.args.amount_wad,
        }:null}; break;
      case "/api/demo/time": payload={status:"ok"}; break;
      default: throw new Error("Unexpected HTTP "+url.pathname);
    }
    return new Response(JSON.stringify(payload),{status:200,headers:{"Content-Type":"application/json"}});
  };
  const client = new WalletClient({registry,getProvider:()=>provider,domain:()=>"localhost",fetcher,now:()=>now,pause:async()=>{},receiptAttempts:1});
  return {client,provider,calls,message, mutate:(fn:typeof mutate)=>{mutate=fn;}, allowance:(n:bigint)=>{allowance=n;}, advance:(ms:number)=>{now+=ms;},
    mismatch:()=>{mismatch=true;}, failConfirm:(v:boolean)=>{failConfirm=v;}, holdPdf:(v:Promise<void>)=>{holdPdf=v;},
    async ready(){await client.connect();await client.authenticate();},
    count(method:string){return provider.requests.filter(r=>r.method===method).length;},
  };
}
test("canonical handoff supports both chains and exports signing functions only", () => {
  const publicRegistry=walletRegistry(registry,{local:0,sepolia:123});
  assert.equal(publicRegistry.networks.sepolia.fromBlock,123);
  assert.equal(new Interface(publicRegistry.contracts.LendingPool.abi!).getFunction("borrow")?.selector, abi("LendingPool").getFunction("borrow")?.selector);
  assert.equal(new Interface(publicRegistry.contracts.LendingPool.abi!).getFunction("owner"),null);
});
test("nonce is signed as exact EIP-191 UTF-8 bytes; session is backend-issued; no tx is broadcast",async()=>{
  const h=harness(); await h.ready();
  const sign=h.provider.requests.find(r=>r.method==="personal_sign")!;
  assert.equal(toUtf8String((sign.params as string[])[0]),h.message);
  assert.equal((sign.params as string[])[1],account.address);
  assert.equal(h.client.getSnapshot().session?.token,"opaque-test-session");
  assert.equal(h.count("eth_sendTransaction"),0);
  assert.equal(h.calls.find(c=>c.path.endsWith("verify"))?.auth,null);
});
test("reject signature from another account before verify",async()=>{
  const h=harness();await h.client.connect();h.provider.signedBy=other;
  await assert.rejects(h.client.authenticate());
  assert.equal(h.client.getSnapshot().session,null);
  assert.equal(h.calls.filter(c=>c.path.endsWith("verify")).length,0);
});
test("borrow order is encrypted PDF/CID -> prepare -> wallet -> backend binding",async()=>{
  const h=harness();await h.ready();
  const op:Operation={action:"BORROW",args:{amount_wad:(100n*WAD).toString()},assetDescription:"Test collateral"};
  await h.client.prepare(op);
  assert.deepEqual(h.calls.slice(-2).map(c=>c.path),["/api/ipfs/create-agreement","/api/transactions/prepare"]);
  assert.equal(h.client.getSnapshot().quote?.cid,CID);
  assert.equal(h.count("eth_sendTransaction"),0);
  await h.client.send();
  assert.equal(h.count("eth_sendTransaction"),1);
  assert.equal(h.client.getSnapshot().records[0].status,"confirmed");
  assert.equal(h.client.getSnapshot().records[0].cid,CID);
});
for(const [label, mutate] of Object.entries({
  chain:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.chainId=1;},
  recipient:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.to=other.address;},
  sender:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.from=other.address;},
  calldata:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.data="0xdeadbeef";},
  value:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.value=1;},
  fee:(q:ReturnType<typeof quote>)=>{q.gas_quote.max_fee_wei="1";},
  gas:(q:ReturnType<typeof quote>)=>{q.unsignedTransaction.gas=1;},
  allowanceToken:(q:ReturnType<typeof quote>)=>{q.allowance.token_address=other.address;},
  allowanceAmount:(q:ReturnType<typeof quote>)=>{q.allowance.amount_wad="1";},
  context:(q:ReturnType<typeof quote>)=>{q.context.network="sepolia";},
})) test("block malformed quote: "+label,async()=>{
  const h=harness();await h.ready();h.mutate(mutate);await assert.rejects(h.client.prepare(deposit));
  assert.equal(h.count("eth_sendTransaction"),0);assert.equal(h.client.getSnapshot().quote,null);
});
test("approval is a separately reviewed tx; main deposit is prepared again after receipt",async()=>{
  const h=harness();h.allowance(0n);await h.ready();await h.client.prepare(deposit);
  assert.equal(h.client.getSnapshot().quote?.approvalRequired,true);
  await assert.rejects(h.client.send());
  await h.client.prepareApproval();
  assert.equal(h.client.getSnapshot().quote?.operation.action,"APPROVE_MYUSDT");
  await h.client.send();
  assert.equal(h.count("eth_sendTransaction"),1);
  await h.client.prepare(deposit);
  assert.equal(h.client.getSnapshot().quote?.approvalRequired,false);
  assert.equal(h.count("eth_sendTransaction"),1);
});
test("NFT token ID zero remains valid in the approval flow",async()=>{
  const h=harness();await h.ready();
  await h.client.prepare({action:"DEPOSIT_COLLATERAL",args:{is_nft:true,collateral_amount_or_token_id:"0"}});
  await h.client.prepareApproval();
  assert.equal(h.client.getSnapshot().quote?.operation.args.token_id,"0");
});
test("MetaMask rejection preserves no successful record and never confirms",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.provider.rejectSend={code:4001};
  await assert.rejects(h.client.send());assert.match(h.client.getSnapshot().error,/từ chối/);
  assert.equal(h.client.getSnapshot().records.length,0);
  assert.equal(h.calls.filter(c=>c.path.endsWith("/confirm")).length,0);
});
test("receipt timeout -> confirmation retry uses same hash and never rebroadcasts",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.provider.receipt=null;await h.client.send();
  assert.equal(h.client.getSnapshot().records[0].status,"pending");
  await assert.rejects(h.client.prepare(deposit));
  h.provider.receipt={status:"0x1",transactionHash:HASH};await h.client.retryConfirmation(HASH);
  assert.equal(h.count("eth_sendTransaction"),1);assert.equal(h.client.getSnapshot().records[0].status,"confirmed");
});
test("backend outage can be retried without resending transaction",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.failConfirm(true);await assert.rejects(h.client.send());
  assert.equal(h.client.getSnapshot().records[0].status,"pending");h.failConfirm(false);await h.client.retryConfirmation(HASH);
  assert.equal(h.count("eth_sendTransaction"),1);assert.equal(h.client.getSnapshot().records[0].status,"confirmed");
});
test("reverted receipt is failed and never sent to success confirmation API",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.provider.receipt={status:"0x0",transactionHash:HASH};
  await assert.rejects(h.client.send());assert.equal(h.client.getSnapshot().records[0].status,"failed");
  assert.equal(h.calls.filter(c=>c.path.endsWith("/confirm")).length,0);
  assert.match(h.client.getSnapshot().notice,/revert/);
});
test("borrow cannot report success with a mismatched CID binding",async()=>{
  const h=harness();await h.ready();await h.client.prepare({action:"BORROW",args:{amount_wad:WAD.toString()},assetDescription:"Test"});
  h.mismatch();await assert.rejects(h.client.send());assert.equal(h.client.getSnapshot().records[0].status,"pending");
});
test("account, network, mode and expiry each clear session, quote and private CID",async()=>{
  for(const change of [(h:ReturnType<typeof harness>)=>h.provider.emitAccount(other.address),
    (h:ReturnType<typeof harness>)=>{h.provider.chain="0xaa36a7";h.provider.events.get("chainChanged")?.(h.provider.chain);},
    (h:ReturnType<typeof harness>)=>h.client.setMode("sample"),
    (h:ReturnType<typeof harness>)=>{h.advance(3601000);h.client.expire();}]) {
    const h=harness();await h.ready();await h.client.prepare({action:"BORROW",args:{amount_wad:WAD.toString()},assetDescription:"Test"});
    change(h);assert.equal(h.client.getSnapshot().session,null);assert.equal(h.client.getSnapshot().quote,null);assert.equal(h.client.getSnapshot().agreementCid,"");
    await assert.rejects(h.client.send());assert.equal(h.count("eth_sendTransaction"),0);
  }
});
test("late PDF response after account switch cannot prepare or expose old CID",async()=>{
  const h=harness();await h.ready();let release!:()=>void;h.holdPdf(new Promise<void>(r=>{release=r;}));
  const pending=h.client.prepare({action:"BORROW",args:{amount_wad:WAD.toString()},assetDescription:"Test"});
  while(!h.calls.some(c=>c.path.endsWith("create-agreement"))) await new Promise(r=>setTimeout(r,0));
  h.provider.emitAccount(other.address);release();await assert.rejects(pending);
  assert.equal(h.client.getSnapshot().agreementCid,"");assert.equal(h.calls.filter(c=>c.path.endsWith("/prepare")).length,0);
});
test("pending confirmation is bound to original API origin",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.provider.receipt=null;await h.client.send();
  h.client.configure("http://localhost:9999");await h.client.authenticate();
  await assert.rejects(h.client.retryConfirmation(HASH),/API/);
  assert.equal(h.count("eth_sendTransaction"),1);
});
test("aged or tampered review is rejected before wallet broadcast",async()=>{
  const h=harness();await h.ready();await h.client.prepare(deposit);h.advance(120001);await assert.rejects(h.client.send());
  await h.client.prepare(deposit);h.client.getSnapshot().quote!.tx.value="0x1";await assert.rejects(h.client.send());
  assert.equal(h.count("eth_sendTransaction"),0);
});
test("local demo time/price are blocked on Sepolia even for an Admin session",async()=>{
  const h=harness();await h.ready();await h.client.switchNetwork("sepolia");await h.client.authenticate();
  await assert.rejects(h.client.advanceTime(30));await assert.rejects(h.client.prepare({action:"MOCK_ORACLE_MULTIPLIER",args:{multiplier_bps:6000}}));
  assert.equal(h.calls.filter(c=>c.path==="/api/demo/time").length,0);assert.equal(h.count("eth_sendTransaction"),0);
});
test("scope disposal removes provider listeners",async()=>{
  const h=harness();await h.ready();assert.equal(h.provider.events.size,3);h.client.dispose();assert.equal(h.provider.events.size,0);
});
test("pending wallet prompt has a friendly message",()=>assert.match(walletError({code:-32002}),/đang chờ/));
test("validator never passes an injected nonce or arbitrary transaction fields to MetaMask",()=>{
  const raw=quote(deposit);Object.assign(raw.unsignedTransaction,{nonce:99,private_key:"not-a-real-key"});
  const result=validatePrepared(raw,registry,"local",account.address,deposit,0);
  assert.equal(result.tx.nonce,undefined);assert.equal(result.tx.private_key,undefined);
});
