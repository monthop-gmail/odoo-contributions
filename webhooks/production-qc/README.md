# Production & QC Webhook

FastAPI webhook server สำหรับรับ Production และ QC Records เข้า Odoo

## Endpoints

- `POST /webhook/production` - รับข้อมูลการผลิตจากเครื่องจักร
- `POST /webhook/qc` - รับข้อมูลตรวจสอบคุณภาพ
- `GET /health` - Health check

## การติดตั้ง

### Docker

```bash
docker build -t odoo-production-qc-webhook .
docker run -p 8000:8000 \
  -e ODOO_URL=https://your-odoo.com \
  -e ODOO_DB=production \
  -e ODOO_USERNAME=api-user \
  -e ODOO_PASSWORD=api-key \
  -e API_KEY=your-secret-key \
  odoo-production-qc-webhook
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ODOO_URL` | Odoo instance URL | `https://my-odoo.com` |
| `ODOO_DB` | Database name | `production` |
| `ODOO_USERNAME` | API username | `api-user` |
| `ODOO_PASSWORD` | API password/key | `secret` |
| `API_KEY` | Webhook API key | `your-secret-key` |

## Payload Examples

### Production Webhook

```json
{
  "work_order_id": "WO-2026-001",
  "product_code": "PROD-001",
  "quantity": 100,
  "operator_id": "OP-001",
  "timestamp": "2026-02-27T09:00:00+07:00",
  "machine_id": "MC-001",
  "lot_number": "LOT-20260227-001"
}
```

### QC Webhook

```json
{
  "lot_number": "LOT-20260227-001",
  "product_code": "PROD-001",
  "quantity_checked": 100,
  "quantity_passed": 98,
  "quantity_rejected": 2,
  "inspector_id": "QC-001",
  "timestamp": "2026-02-27T10:00:00+07:00",
  "measurements": [
    {
      "parameter": "weight",
      "value": 500.5,
      "spec_min": 495,
      "spec_max": 505,
      "result": "pass"
    }
  ],
  "notes": "Quality check passed"
}
```

## Documentation

ดูคู่มือเพิ่มเติมที่: [../../docs/webhook-middleware-guide.md](../../docs/webhook-middleware-guide.md)
