import { Interface, getAddress, toQuantity, type InterfaceAbi } from "ethers";

export type NetworkId = "local" | "sepolia";
export const CHAINS = { local: 31337, sepolia: 11155111 } as const;
export interface ContractRecord { address: string; abi?: InterfaceAbi; abiPath?: string }
export interface DeploymentRegistry {
  contracts: Record<string, ContractRecord>;
  networks: Record<NetworkId, { chainId: number; fromBlock?: number; contracts: Record<string, ContractRecord> }>;
}
export type Action = "APPROVE_MYUSDT" | "APPROVE_COLLATERAL_NFT" | "DEPOSIT_LENDER" | "WITHDRAW_LENDER" | "TRANSFER_LENDING_POSITION_NFT" | "DEPOSIT_COLLATERAL" | "WITHDRAW_COLLATERAL" | "BORROW" | "REPAY" | "LIQUIDATE" | "FAUCET_MYUSDT" | "MOCK_ORACLE_MULTIPLIER";
export interface Operation {
  action: Action; args: Record<string, string | number | boolean>;
  assetDescription?: string; repayAll?: boolean;
}
export const ACTION_NAMES: Record<Action, string> = {
  APPROVE_MYUSDT: "Cấp quyền MyUSDT", APPROVE_COLLATERAL_NFT: "Cấp quyền NFT thế chấp",
  DEPOSIT_LENDER: "Gửi MyUSDT", WITHDRAW_LENDER: "Rút vốn và lãi",
  TRANSFER_LENDING_POSITION_NFT: "Chuyển NFT vị thế", DEPOSIT_COLLATERAL: "Khóa tài sản thế chấp",
  WITHDRAW_COLLATERAL: "Rút tài sản thế chấp", BORROW: "Vay MyUSDT", REPAY: "Trả nợ MyUSDT",
  LIQUIDATE: "Thanh lý khoản vay", FAUCET_MYUSDT: "Nhận MyUSDT thử nghiệm", MOCK_ORACLE_MULTIPLIER: "Đổi giá Oracle local",
};
export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Phản hồi API không hợp lệ.");
  return value as Record<string, unknown>;
}
export function uint(value: unknown): bigint {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return BigInt(value);
  if (typeof value === "bigint" && value >= 0n) return value;
  if (typeof value === "string" && /^(0x[0-9a-fA-F]+|[0-9]+)$/.test(value)) {
    const n = BigInt(value); if (n < 1n << 256n) return n;
  }
  throw new Error("Số nguyên không hợp lệ trong dữ liệu giao dịch.");
}
export function address(value: unknown) {
  if (typeof value !== "string") throw new Error("Địa chỉ ví không hợp lệ.");
  return getAddress(value);
}
export function same(a: unknown, b: unknown) { return address(a).toLowerCase() === address(b).toLowerCase(); }
export function contract(registry: DeploymentRegistry, network: NetworkId, name: string) {
  const deployment = registry.networks[network];
  const entry = deployment?.contracts[name];
  if (deployment?.chainId !== CHAINS[network] || !entry) throw new Error("Thiếu bàn giao contract " + name + " trên " + network + ".");
  const abi = entry.abi || registry.contracts[name]?.abi;
  if (!abi?.length) throw new Error("Thiếu ABI " + name + ".");
  return { address: address(entry.address), abi };
}
export function expectedCall(registry: DeploymentRegistry, network: NetworkId, account: string, op: Operation) {
  const a = op.args;
  const pool = contract(registry, network, "LendingPool").address;
  const positive = (v: unknown) => { const n = uint(v); if (!n) throw new Error("Số tiền phải lớn hơn 0."); return n; };
  let name = "LendingPool", method: string, args: unknown[];
  switch (op.action) {
    case "APPROVE_MYUSDT": name = "MyUSDT"; method = "approve"; args = [pool, positive(a.amount_wad)]; break;
    case "APPROVE_COLLATERAL_NFT": name = "CollateralNFT"; method = "approve"; args = [pool, uint(a.token_id)]; break;
    case "DEPOSIT_LENDER": method = "depositLender"; args = [positive(a.amount_wad)]; break;
    case "WITHDRAW_LENDER": method = "withdrawLender"; args = [uint(a.position_id), positive(a.amount_wad)]; break;
    case "TRANSFER_LENDING_POSITION_NFT": {
      name = "LendingPositionNFT"; method = "safeTransferFrom(address,address,uint256)";
      const to = address(a.recipient_address); if (/^0x0{40}$/i.test(to)) throw new Error("Không chuyển NFT đến ví 0.");
      args = [address(account), to, uint(a.position_id)]; break;
    }
    case "DEPOSIT_COLLATERAL":
      if (typeof a.is_nft !== "boolean") throw new Error("Chọn loại tài sản thế chấp.");
      method = "depositCollateral"; args = [a.is_nft ? uint(a.collateral_amount_or_token_id) : positive(a.collateral_amount_or_token_id), a.is_nft]; break;
    case "WITHDRAW_COLLATERAL": method = "withdrawCollateral"; args = []; break;
    case "BORROW": method = "borrow"; if (typeof a.agreement_cid !== "string" || !a.agreement_cid) throw new Error("Thiếu CID thỏa thuận vay."); args = [positive(a.amount_wad), a.agreement_cid]; break;
    case "REPAY": method = "repay"; args = [positive(a.amount_wad)]; break;
    case "LIQUIDATE": method = "liquidate"; args = [address(a.borrower_address)]; break;
    case "FAUCET_MYUSDT": name = "MyUSDT"; method = "faucet"; args = [address(a.recipient_address || account), positive(a.amount_wad)]; break;
    case "MOCK_ORACLE_MULTIPLIER":
      if (network !== "local") throw new Error("Không đổi giá Oracle trên Sepolia.");
      name = "PriceOracle"; method = "setPriceMultiplierBps"; args = [uint(a.multiplier_bps)]; break;
    default: throw new Error("Thao tác chưa được hỗ trợ.");
  }
  const entry = contract(registry, network, name);
  return { to: entry.address, data: new Interface(entry.abi).encodeFunctionData(method, args), contractName: name };
}
export interface Prepared {
  intentId: string; operation: Operation; network: NetworkId; account: string; epoch: number; quotedAt: number;
  tx: Record<string, string>; gas: Record<string, unknown>; preview: Record<string, unknown>;
  interest: Record<string, unknown> | null; allowance: Record<string, unknown>;
  approvalRequired: boolean; cid?: string; blockNumber: number;
}
export function validatePrepared(raw: unknown, registry: DeploymentRegistry, network: NetworkId, account: string, operation: Operation, epoch: number, now = Date.now()): Prepared {
  const body = object(raw), context = object(body.context), tx = object(body.unsignedTransaction);
  const allowance = object(body.allowance), gas = object(body.gas_quote), ready = object(body.availability);
  const expected = expectedCall(registry, network, account, operation);
  if (body.signing !== "client_wallet" || typeof body.intent_id !== "string" || !body.intent_id ||
      context.network !== network || uint(context.chain_id) !== BigInt(CHAINS[network]) || context.action !== operation.action ||
      !same(context.account, account) || !same(tx.from, account) || !same(tx.to, expected.to) ||
      uint(tx.chainId) !== BigInt(CHAINS[network]) || uint(tx.value) !== 0n ||
      typeof tx.data !== "string" || tx.data.toLowerCase() !== expected.data.toLowerCase()) throw new Error("Payload khác mạng, ví, contract hoặc nội dung đã yêu cầu. Đã chặn ký.");
  if (ready.ready !== true || !Array.isArray(ready.missing_contracts) || ready.missing_contracts.length) throw new Error("Backend báo contract chưa sẵn sàng.");
  if (typeof allowance.approval_required !== "boolean") throw new Error("API thiếu trạng thái cấp quyền.");
  const approval = allowance.approval_required;
  const action = operation.action, args = operation.args;
  const erc20 = ["DEPOSIT_LENDER", "REPAY", "LIQUIDATE"].includes(action) || (action === "DEPOSIT_COLLATERAL" && args.is_nft === false);
  const nft = action === "DEPOSIT_COLLATERAL" && args.is_nft === true;
  if (erc20 || nft) {
    const token = contract(registry, network, nft ? "CollateralNFT" : "MyUSDT").address;
    if (!same(allowance.token_address, token) || !same(allowance.spender_address, contract(registry, network, "LendingPool").address)) throw new Error("Allowance không khớp token hoặc Pool đã bàn giao.");
    if (nft) {
      if (uint(allowance.token_id) !== uint(args.collateral_amount_or_token_id)) throw new Error("Allowance sai mã NFT.");
    } else {
      const required = uint(allowance.amount_wad);
      if (!required || (action !== "LIQUIDATE" && required !== uint(args.amount_wad ?? args.collateral_amount_or_token_id))) throw new Error("Allowance sai số tiền thao tác.");
      if (approval !== (uint(allowance.current_allowance_wad) < required)) throw new Error("Trạng thái allowance không nhất quán.");
    }
  } else if (approval) throw new Error("Thao tác này không yêu cầu cấp quyền token.");
  const price = uint(tx.gasPrice);
  if (uint(gas.gas_price_wei) !== price) throw new Error("Giá gas không khớp giao dịch.");
  const rpcTx: Record<string, string> = { from: address(account), to: expected.to, data: expected.data, value: "0x0", chainId: toQuantity(CHAINS[network]), gasPrice: toQuantity(price) };
  if (!approval) {
    const estimated = uint(gas.estimated_gas), limit = uint(gas.gas_limit);
    if (gas.estimation_status !== "ESTIMATED" || estimated === 0n || limit < estimated || uint(tx.gas) !== limit ||
        uint(gas.estimated_fee_wei) !== estimated * price || uint(gas.max_fee_wei) !== limit * price) throw new Error("Ước lượng phí gas không khớp payload.");
    rpcTx.gas = toQuantity(limit);
  } else if (gas.estimation_status !== "PENDING_APPROVAL") throw new Error("Cần chuẩn bị lại sau bước cấp quyền.");
  return { intentId: body.intent_id, operation: { ...operation, args: { ...operation.args } }, network, account: address(account), epoch, quotedAt: now,
    tx: rpcTx, gas, preview: object(body.preview), interest: body.interest_quote ? object(body.interest_quote) : null,
    allowance, approvalRequired: approval, cid: typeof operation.args.agreement_cid === "string" ? operation.args.agreement_cid : undefined,
    blockNumber: Number(uint(context.block_number)) };
}
export function explorerTx(network: NetworkId, hash: string) {
  return network === "sepolia" && /^0x[0-9a-fA-F]{64}$/.test(hash) ? "https://sepolia.etherscan.io/tx/" + hash : null;
}
