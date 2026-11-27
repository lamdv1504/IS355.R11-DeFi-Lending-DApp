@echo off
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

echo [Q06] Starting Hardhat node on 127.0.0.1:8545...
start "IS355 Hardhat 31337" /D "%ROOT%" cmd /k "npx hardhat node --hostname 127.0.0.1 --port 8545"

echo [Q06] Waiting for Hardhat JSON-RPC...
set "RPC_READY="
for /L %%I in (1,1,45) do (
    curl.exe --silent --show-error --max-time 2 -X POST -H "Content-Type: application/json" --data "{\"jsonrpc\":\"2.0\",\"method\":\"eth_chainId\",\"params\":[],\"id\":1}" http://127.0.0.1:8545 2>nul | findstr /C:"0x7a69" >nul
    if not errorlevel 1 (
        set "RPC_READY=1"
        goto :rpc_ready
    )
    timeout /t 2 /nobreak >nul
)

:rpc_ready
if not defined RPC_READY (
    echo [Q06] ERROR: Hardhat RPC did not become ready within 90 seconds.
    exit /b 1
)

pushd "%ROOT%"
echo [Q06] Deploying contracts, seeding local wallets, and publishing Q04 audit logs...
python scripts\deploy_and_seed.py
if errorlevel 1 (
    echo [Q06] ERROR: Local deploy and seed failed. Backend/frontend were not started.
    popd
    exit /b 1
)

echo [Q06] Starting FastAPI on http://127.0.0.1:8000...
start "IS355 FastAPI" /D "%ROOT%" cmd /k "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo [Q06] Starting Next.js on http://127.0.0.1:3000...
start "IS355 Next.js" /D "%ROOT%\frontend" cmd /k "npm run dev -- --hostname 127.0.0.1 --port 3000"
popd
echo [Q06] All services started in separate terminal windows.
endlocal
