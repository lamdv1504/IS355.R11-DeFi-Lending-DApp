import test from "node:test";
import assert from "node:assert/strict";
import { apiRequest, fetchRateAnalytics, fetchWalletSnapshot, type HubConnection } from "../src/lib/ipfs-hub.ts";
const connection:HubConnection={mode:"api",baseUrl:"http://localhost:8000",token:"test-token",network:"sepolia",fromBlock:123};
const account="0x0000000000000000000000000000000000000001";
test("live read URLs carry selected chain and bounded event start block",async()=>{
  const urls:string[]=[];
  const fetcher:typeof fetch=async(input)=>{urls.push(String(input));return new Response("{}");};
  await apiRequest(connection,"/api/accounts/"+account+"/snapshot",{},fetcher);
  const url=new URL(urls[0]);assert.equal(url.searchParams.get("network"),"sepolia");assert.equal(url.searchParams.get("from_block"),"123");
  await assert.rejects(apiRequest(connection,"/api/pool?network=local",{},fetcher));
  assert.equal(urls.length,1);
});
test("live analytics refuses a response for a different chain",async()=>{
  const fetcher:typeof fetch=async()=>new Response(JSON.stringify({network:"local",chain_id:31337,series:[]}));
  await assert.rejects(fetchRateAnalytics(connection,6,undefined,fetcher),/khớp/);
});
test("live wallet snapshot refuses data for a different wallet",async()=>{
  const fetcher:typeof fetch=async()=>new Response(JSON.stringify({network:"sepolia",chain_id:11155111,wallet_address:"0x0000000000000000000000000000000000000002"}));
  await assert.rejects(fetchWalletSnapshot(connection,account,undefined,fetcher),/khớp/);
});
test("HTTP 401 notifies shared wallet to invalidate its private session",async()=>{
  let called=0;const c={...connection,onUnauthorized:()=>{called++;}};
  await assert.rejects(apiRequest(c,"/api/ipfs/documents",{},async()=>new Response('{"detail":"expired"}',{status:401})));
  assert.equal(called,1);
});
