import os
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from main import execute_gcat_treasury_settlement, BLNK_URL, MOOV_ACH_URL, FINERACT_URL, FINERACT_AUTH

app = FastAPI(title="SF Emerald Dynasty Trust — Fiduciary Treasury Portal")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>SF Emerald Dynasty Trust — Fiduciary Treasury</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b1220; color: #e2e8f0; margin: 0; padding: 24px; }
  .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
  .badge { background: #065f46; color: #6ee7b7; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 20px; }
  h2 { font-size: 15px; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; margin-top: 0; }
  .metric { font-size: 28px; font-weight: 700; color: #34d399; margin: 8px 0; }
  .sub { font-size: 12px; color: #64748b; }
  label { display: block; font-size: 12px; color: #94a3b8; margin-top: 12px; }
  input, select { width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #334155; color: #f8fafc; padding: 8px 10px; border-radius: 6px; margin-top: 4px; }
  button { width: 100%; margin-top: 16px; background: #10b981; color: #06281e; font-weight: 700; border: none; padding: 10px; border-radius: 6px; cursor: pointer; }
  button:hover { background: #34d399; }
  .btn-secondary { background: #3b82f6; color: #fff; }
  pre { background: #090d16; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; color: #93c5fd; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <strong style="font-size:18px;">SF EMERALD DYNASTY TRUST</strong>
      <div class="sub">Fiduciary Treasury & Real-Ledger Command Desk (Fineract + Blnk + Moov ISO 20022)</div>
    </div>
    <span class="badge">MAKER-CHECKER ENFORCED</span>
  </div>

  <div class="grid">
    <div class="card">
      <h2>1. Reserve & Spendable Ledger</h2>
      <div class="sub">GCAT Source Position (Stellar Ledger 65297375)</div>
      <div class="metric">$250,000.00</div>
      <div class="sub">Fineract Destination Spendable Balance: <strong id="finBal" style="color:#f8fafc;">Loading...</strong></div>
      <button onclick="runSettlement()">Execute $250,000 UETR Settlement</button>
      <pre id="settleOut">Ready to bind UETR + pacs.008 + NACHA CCD.</pre>
    </div>

    <div class="card">
      <h2>2. Outbound Payment Execution</h2>
      <form onsubmit="submitDisbursement(event)">
        <label>Payment Rail</label>
        <select id="paymentTypeId">
          <option value="1">ISO 20022 Wire (pacs.008)</option>
          <option value="2">Moov NACHA CCD Batch</option>
          <option value="3">Fiduciary Physical Check / Draft</option>
        </select>
        <label>Beneficiary / Payee Name</label>
        <input id="payee" placeholder="Authorized Trust Payee" required />
        <label>Amount (USD)</label>
        <input id="amount" type="number" step="0.01" placeholder="5000.00" required />
        <label>Custom Industry Fee (USD)</label>
        <input id="fee" type="number" step="0.01" value="25.00" />
        <label>Check Serial # / UETR Reference</label>
        <input id="ref" placeholder="CHK-1001 or UETR" required />
        <button type="submit" class="btn-secondary">Queue Disbursement for Sign-Off</button>
      </form>
    </div>

    <div class="card">
      <h2>3. Fiduciary Sign-Off & UETR Audit</h2>
      <div class="sub">Pending Maker-Checker Queue & NACHA Artifacts</div>
      <pre id="auditOut">Fetching Fineract Maker-Checker queue & Moov files...</pre>
      <button onclick="refreshStatus()">Refresh Live Ledger & Queue</button>
    </div>
  </div>

<script>
async function refreshStatus() {
  const res = await fetch('/api/status');
  const data = await res.json();
  document.getElementById('finBal').innerText = data.fineract_balance || 'Initializing Fineract...';
  document.getElementById('auditOut').innerText = JSON.stringify(data, null, 2);
}
async function runSettlement() {
  document.getElementById('settleOut').innerText = 'Executing 5-step atomic UETR settlement...';
  const res = await fetch('/api/settle', { method: 'POST' });
  document.getElementById('settleOut').innerText = JSON.stringify(await res.json(), null, 2);
  refreshStatus();
}
async function submitDisbursement(e) {
  e.preventDefault();
  const body = new URLSearchParams({
    paymentTypeId: document.getElementById('paymentTypeId').value,
    payee: document.getElementById('payee').value,
    amount: document.getElementById('amount').value,
    fee: document.getElementById('fee').value,
    ref: document.getElementById('ref').value
  });
  const res = await fetch('/api/disburse', { method: 'POST', body });
  document.getElementById('auditOut').innerText = JSON.stringify(await res.json(), null, 2);
  refreshStatus();
}
refreshStatus();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_TEMPLATE

@app.get("/api/status")
def status():
    out = {"fineract_balance": None, "pending_approvals": [], "moov_files": []}
    try:
        r = requests.get(f"{FINERACT_URL}/savingsaccounts/1", auth=FINERACT_AUTH, headers={"Fineract-Platform-TenantId": "default"}, verify=False, timeout=5)
        if r.ok:
            out["fineract_balance"] = f"${r.json().get('availableBalance', 0):,.2f} USD"
    except Exception as e:
        out["fineract_error"] = str(e)
    try:
        m = requests.get(f"{MOOV_ACH_URL}/files", timeout=5)
        if m.ok:
            out["moov_files"] = m.json()
    except Exception as e:
        out["moov_error"] = str(e)
    return JSONResponse(out)

@app.post("/api/settle")
def settle():
    try:
        return JSONResponse(execute_gcat_treasury_settlement())
    except Exception as e:
        return JSONResponse({"status": "ERROR", "detail": str(e)}, status_code=500)

@app.post("/api/disburse")
def disburse(paymentTypeId: int = Form(...), payee: str = Form(...), amount: float = Form(...), fee: float = Form(0.0), ref: str = Form(...)):
    total = round(amount + fee, 2)
    payload = {
        "locale": "en",
        "dateFormat": "dd MMMM yyyy",
        "transactionDate": "23 November 2026",
        "transactionAmount": total,
        "paymentTypeId": paymentTypeId,
        "receiptNumber": ref,
        "note": f"Payee: {payee} | Principal: ${amount:.2f} | Fee: ${fee:.2f}"
    }
    try:
        r = requests.post(f"{FINERACT_URL}/savingsaccounts/1/transactions?command=withdrawal", json=payload, auth=FINERACT_AUTH, headers={"Fineract-Platform-TenantId": "default"}, verify=False, timeout=10)
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"status": "ERROR", "detail": str(e)}, status_code=500)
