@echo off
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PYTHON_EXE=python"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
set "IPFS_READY="

where ipfs.exe >nul 2>nul
if errorlevel 1 (
    echo [Q06] IPFS Kubo CLI not found; Q04 will use its local fallback store.
    call :fallback_if_kubo_unavailable
) else (
    curl.exe --silent --max-time 2 -X POST http://127.0.0.1:5001/api/v0/id >nul 2>nul
    if errorlevel 1 (
        echo [Q06] Starting optional IPFS Kubo daemon...
        start "IS355 IPFS Kubo" /D "%ROOT%" cmd /k "ipfs daemon"
        set "IPFS_READY="
        for /L %%I in (1,1,10) do (
            curl.exe --silent --max-time 2 -X POST http://127.0.0.1:5001/api/v0/id 2>nul | findstr /C:"ID" >nul
            if not errorlevel 1 (
                set "IPFS_READY=1"
            )
            timeout /t 1 /nobreak >nul
        )
        if not defined IPFS_READY (
            echo [Q06] Kubo API is unavailable; continuing with the local fallback store.
            call :fallback_if_kubo_unavailable
        )
    ) else (
        echo [Q06] Existing IPFS Kubo daemon is ready.
    )
)

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
"%PYTHON_EXE%" scripts\deploy_and_seed.py
if errorlevel 1 (
    echo [Q06] ERROR: Local deploy and seed failed. Backend/frontend were not started.
    popd
    exit /b 1
)

echo [Q06] Starting FastAPI on http://127.0.0.1:8000...
start "IS355 FastAPI" /D "%ROOT%" cmd /k ""%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo [Q06] Starting Next.js on http://127.0.0.1:3000...
start "IS355 Next.js" /D "%ROOT%\frontend" cmd /k "npm run dev -- --hostname 127.0.0.1 --port 3000"
popd
echo [Q06] All services started in separate terminal windows.
endlocal
goto :eof

:fallback_if_kubo_unavailable
if /I "%IPFS_PROVIDER%"=="kubo" (
    set "IPFS_PROVIDER=local_fallback"
    echo [Q06] IPFS_PROVIDER changed to local_fallback for this run.
    exit /b 0
)
findstr /R /I /C:"^[ ]*IPFS_PROVIDER[ ]*=[ ]*kubo[ ]*$" "%ROOT%\.env" >nul 2>nul
if not errorlevel 1 (
    set "IPFS_PROVIDER=local_fallback"
    echo [Q06] .env requests Kubo but the daemon is unavailable; using local_fallback for this run.
)
exit /b 0
