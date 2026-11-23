# SF Emerald Dynasty Trust — Fiduciary Treasury Pipeline

Self-hosted, 100% open-source Fiduciary Treasury & Real-Ledger management stack transitioning settled GCAT reserve records (**Stellar Ledger `65297375` — $250,000.00 USD**) through **Blnk**, **ISO 20022 (`pacs.008` + UETR)**, **Moov (`moov-io/ach`)**, and **Apache Fineract**, fronted by a custom **ToolJet** Fiduciary Portal behind a **Cloudflare Zero Trust Tunnel**.

## Quickstart Deployment
1. Copy `.env.example` to `.env` locally and populate your credentials:
   ```bash
   cp .env.example .env
   ```
2. Generate ToolJet keys (`openssl rand -hex 64` and `openssl rand -hex 32`) and paste into `.env`.
3. Launch all services:
   ```bash
   mkdir -p exports/iso20022 exports/nacha
   docker compose up -d
   ```
4. Access your **ToolJet Fiduciary Portal** via your private **Cloudflare Zero Trust** URL (or `http://127.0.0.1:8082`) and connect REST API data sources to `http://blnk:5001`, `http://moov-ach:8080`, and `https://fineract:8443/fineract-provider/api/v1`.
