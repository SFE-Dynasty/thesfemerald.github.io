import os
import uuid
import requests
from datetime import datetime, timezone

BLNK_URL = os.getenv("BLNK_URL", "http://blnk:5001")
MOOV_ACH_URL = os.getenv("MOOV_ACH_URL", "http://moov-ach:8080")
FINERACT_URL = os.getenv("FINERACT_URL", "https://fineract:8443/fineract-provider/api/v1")
FINERACT_AUTH = (os.getenv("FINERACT_USER", "mifos"), os.getenv("FINERACT_PASS", "password"))

def execute_gcat_treasury_settlement(
    amount_cents: int = int(os.getenv("SETTLEMENT_AMOUNT_CENTS", "25000000")),
    gcat_ledger_seq: str = os.getenv("GCAT_LEDGER_SEQ", "65297375"),
    gcat_tx_hash: str = os.getenv("GCAT_TX_HASH", "REPLACE_WITH_TX_HASH"),
    gcat_op_id: str = os.getenv("GCAT_OP_ID", "REPLACE_WITH_OP_ID"),
    fineract_destination_account_id: int = 1
):
    # 1. Mint 36-char UETR & derive 15-char NACHA Type 6 Field 7 join key
    uetr = str(uuid.uuid4())
    nacha_join_key = uetr.replace("-", "")[:15]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    amount_usd = f"{amount_cents / 100:.2f}"

    # 2. Post INFLIGHT atomic hold in Blnk Ledger
    blnk_payload = {
        "amount": amount_cents,
        "precision": 100,
        "reference": uetr,
        "currency": "USD",
        "source": "@gcat_treasury_reserve",
        "destination": "@trust_fiat_destination",
        "inflight": True,
        "meta_data": {
            "uetr": uetr,
            "nacha_join_key": nacha_join_key,
            "iso_msg": "pacs.008.001.08",
            "stellar_ledger": gcat_ledger_seq,
            "stellar_tx_hash": gcat_tx_hash,
            "stellar_op_id": gcat_op_id
        }
    }
    blnk_res = requests.post(f"{BLNK_URL}/transactions", json=blnk_payload, timeout=15)
    blnk_res.raise_for_status()
    blnk_tx_id = blnk_res.json()["transaction_id"]

    # 3. Generate ISO 20022 pacs.008.001.08 XML artifact
    pacs008_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <GrpHdr>
      <MsgId>SFE-{gcat_ledger_seq}-{nacha_join_key}</MsgId>
      <CreDtTm>{timestamp}</CreDtTm>
      <NbOfTxs>1</NbOfTxs>
      <SttlmInf><SttlmMtd>CLRG</SttlmMtd></SttlmInf>
    </GrpHdr>
    <CdtTrfTxInf>
      <PmtId>
        <InstrId>OP-{gcat_op_id}</InstrId>
        <EndToEndId>LEDGER-{gcat_ledger_seq}</EndToEndId>
        <UETR>{uetr}</UETR>
      </PmtId>
      <IntrBkSttlmAmt Ccy="USD">{amount_usd}</IntrBkSttlmAmt>
      <ChrgBr>SLEV</ChrgBr>
      <Dbtr><Nm>SF Emerald Dynasty Trust Reserve</Nm></Dbtr>
      <Cdtr><Nm>SF Emerald Dynasty Trust Destination</Nm></Cdtr>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    os.makedirs("exports/iso20022", exist_ok=True)
    with open(f"exports/iso20022/pacs008_{uetr}.xml", "w", encoding="utf-8") as f:
        f.write(pacs008_xml)

    # 4. Construct NACHA CCD entry via Moov (Addenda05 UETR + Type 6 join key)
    moov_payload = {
        "fileHeader": {
            "immediateDestination": "021000021",
            "immediateOrigin": "123456789",
            "immediateDestinationName": "SFE FIDUCIARY CLEARING",
            "immediateOriginName": "SF EMERALD DYNASTY TRUST"
        },
        "batches": [{
            "batchHeader": {
                "serviceClassCode": 220,
                "companyName": "SFE TRUST",
                "companyIdentification": "1234567890",
                "standardEntryClassCode": "CCD",
                "companyEntryDescription": "TREASURY",
                "effectiveEntryDate": datetime.now(timezone.utc).strftime("%y%m%d"),
                "originatorStatusCode": 1,
                "ODFIIdentification": "02100002"
            },
            "entryDetails": [{
                "transactionCode": 22,
                "RDFIIdentification": "02100002",
                "checkDigit": "1",
                "DFIAccountNumber": "0000000001",
                "amount": amount_cents,
                "identificationNumber": nacha_join_key,
                "individualName": "SFE TRUST DESTINATION",
                "addendaRecordIndicator": 1,
                "addenda05": [{
                    "typeCode": "05",
                    "paymentRelatedInformation": f"UETR/{uetr}/LEDGER/{gcat_ledger_seq}",
                    "sequenceNumber": 1,
                    "entryDetailSequenceNumber": 1
                }]
            }]
        }]
    }
    moov_res = requests.post(f"{MOOV_ACH_URL}/files/create", json=moov_payload, timeout=15)
    moov_res.raise_for_status()

    # 5. Commit Blnk transaction & credit Apache Fineract Destination Ledger
    requests.put(f"{BLNK_URL}/transactions/{blnk_tx_id}/commit", timeout=15).raise_for_status()

    fineract_deposit = {
        "locale": "en",
        "dateFormat": "dd MMMM yyyy",
        "transactionDate": datetime.now(timezone.utc).strftime("%d %B %Y"),
        "transactionAmount": float(amount_usd),
        "paymentTypeId": 1,
        "receiptNumber": uetr,
        "note": f"GCAT Ledger {gcat_ledger_seq} | Hash: {gcat_tx_hash} | JoinKey: {nacha_join_key}"
    }
    fin_res = requests.post(
        f"{FINERACT_URL}/savingsaccounts/{fineract_destination_account_id}/transactions?command=deposit",
        json=fineract_deposit,
        auth=FINERACT_AUTH,
        headers={"Fineract-Platform-TenantId": "default"},
        verify=False,
        timeout=15
    )
    fin_res.raise_for_status()

    return {
        "status": "SETTLED",
        "uetr": uetr,
        "nacha_join_key": nacha_join_key,
        "amount_usd": amount_usd,
        "blnk_tx_id": blnk_tx_id,
        "fineract_tx_id": fin_res.json().get("resourceId")
    }

if __name__ == "__main__":
    print(execute_gcat_treasury_settlement())
