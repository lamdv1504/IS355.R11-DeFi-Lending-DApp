@echo off
REM Start local IPFS Kubo daemon for IS355.R11 DeFi Lending DApp (H03)
REM API: http://127.0.0.1:5001 | Local Gateway: http://127.0.0.1:8080/ipfs/<CID>

where ipfs >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [H03] IPFS Kubo CLI ('ipfs') was not found in PATH.
    echo Install Kubo from https://docs.ipfs.tech/install/command-line/ or run via Docker:
    echo   docker run -d --name is355-ipfs-kubo -p 4001:4001 -p 127.0.0.1:8080:8080 -p 127.0.0.1:5001:5001 ipfs/kubo:latest
    exit /b 1
)

if not exist "%USERPROFILE%\.ipfs\config" (
    echo [H03] Initializing IPFS Kubo local repository...
    ipfs init --profile=local-discovery
)

echo [H03] Configuring local CORS headers for DApp Frontend/Backend...
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin "[\"http://localhost:3000\", \"http://127.0.0.1:3000\", \"http://localhost:5173\", \"http://127.0.0.1:5173\", \"http://127.0.0.1:8000\"]"
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Methods "[\"PUT\", \"POST\", \"GET\"]"

echo [H03] Starting IPFS Kubo daemon (API :5001, Gateway :8080)...
ipfs daemon

