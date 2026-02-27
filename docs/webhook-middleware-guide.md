# Webhook Middleware Guide for Odoo Integration

## คู่มือเลือกใช้ Middleware สำหรับ Webhook เชื่อมต่อ Odoo

---

## 1. Architecture Options

### แบบที่ 1: Direct Connection (ไม่มี Middleware)

```
┌─────────────┐      ┌──────────────────┐      ┌──────┐
│  Machine/   │      │  Your Webhook    │      │ Odoo │
│  Scanner    │ ──→  │  Server          │ ──→  │ API  │
│             │      │  (FastAPI/Flask) │      │      │
└─────────────┘      └──────────────────┘      └──────┘
```

**ข้อดี:**
- ✅ เรียบง่าย ไม่ต้อง maintain เพิ่ม
- ✅ Low latency (น้อย hop)
- ✅ Debug ง่าย
- ✅ เหมาะสำหรับ project ขนาดเล็ก-กลาง

**ข้อเสีย:**
- ❌ Webhook server ต้องรู้ logic การ transform
- ❌ ยากถ้าต้อง connect หลาย systems

---

### แบบที่ 2: ใช้ Middleware

```
┌─────────────┐      ┌─────────────┐      ┌──────────────────┐      ┌──────┐
│  Machine/   │      │  Middleware │      │  Your Webhook    │      │ Odoo │
│  Scanner    │ ──→  │  (n8n/      │ ──→  │  Server          │ ──→  │ API  │
│             │      │   Node-RED) │      │                  │      │      │
└─────────────┘      └─────────────┘      └──────────────────┘      └──────┘
```

**ข้อดี:**
- ✅ แยก concern ชัดเจน (transform vs business logic)
- ✅ Reusable กับหลาย projects
- ✅ มี built-in retry, queue, monitoring
- ✅ เหมาะสำหรับ enterprise / complex integration

**ข้อเสีย:**
- ❌ เพิ่ม complexity
- ❌ ต้อง maintain อีก system
- ❌ เพิ่ม latency

---

## 2. Decision Matrix

| ปัจจัย | ไม่ใช้ Middleware | ใช้ Middleware |
|--------|------------------|---------------|
| **Data Format** | JSON ตรงกับ Odoo | ต้องแปลง format (XML, CSV, etc.) |
| **Systems** | 1-2 systems | 3+ systems |
| **Transform Logic** | ง่ายๆ (field mapping) | ซับซ้อน (aggregation, calculation) |
| **Reliability** | ยอมรับได้ถ้าสูญบ้าง | ต้องมี retry, queue |
| **Team Size** | 1-3 developers | มีทีมเฉพาะ |
| **Timeline** | เร่งด่วน | มีเวลา develop |

---

## 3. Recommended Approach สำหรับ Production/QC Record

### 🎯 แนะนำ: **เริ่มแบบไม่มี Middleware**

**เหตุผล:**
1. Production record มักมี format คงที่จากเครื่องจักร
2. QC record โครงสร้างไม่ซับซ้อน (pass/fail, measurements, timestamps)
3. ลด development time และ complexity
4. ค่อยเพิ่ม middleware ทีหลังถ้าต้องการ

---

## 4. Implementation Example (No Middleware)

### FastAPI Webhook Server

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import xmlrpc.client

app = FastAPI()

# === Data Models ===

class ProductionData(BaseModel):
    work_order_id: str
    product_code: str
    quantity: int
    operator_id: str
    timestamp: datetime
    machine_id: Optional[str] = None

class QCData(BaseModel):
    lot_number: str
    product_code: str
    quantity_checked: int
    quantity_passed: int
    quantity_rejected: int
    inspector_id: str
    timestamp: datetime
    measurements: Optional[List[dict]] = None
    notes: Optional[str] = None

# === Odoo Connection ===

ODOO_URL = "https://your-odoo-instance.com"
ODOO_DB = "production"
ODOO_USERNAME = "api-user"
ODOO_PASSWORD = "api-key"

def get_odoo_proxy():
    return xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

def authenticate():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
    if not uid:
        raise HTTPException(status_code=500, detail="Odoo authentication failed")
    return uid

# === Webhook Endpoints ===

@app.post("/webhook/production")
async def production_webhook(data: ProductionData):
    """รับ Production Record จากเครื่องจักร"""
    
    uid = authenticate()
    proxy = get_odoo_proxy()
    
    # Transform data to Odoo format
    odoo_values = {
        'name': f"WO-{data.work_order_id}",
        'product_id': data.product_code,
        'qty_produced': data.quantity,
        'user_id': data.operator_id,
        'date': data.timestamp.isoformat(),
        'machine_id': data.machine_id,
    }
    
    # Create record in Odoo (mrp.workorder หรือ custom model)
    result = proxy.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'mrp.workorder', 'create',
        [odoo_values]
    )
    
    return {"status": "success", "odoo_id": result}


@app.post("/webhook/qc")
async def qc_webhook(data: QCData):
    """รับ QC Record จากสถานีตรวจสอบ"""
    
    uid = authenticate()
    proxy = get_odoo_proxy()
    
    # Transform data to Odoo format
    odoo_values = {
        'name': f"QC-{data.lot_number}",
        'lot_id': data.lot_number,
        'product_id': data.product_code,
        'qty_checked': data.quantity_checked,
        'qty_passed': data.quantity_passed,
        'qty_rejected': data.quantity_rejected,
        'inspector_id': data.inspector_id,
        'check_date': data.timestamp.isoformat(),
        'notes': data.notes,
    }
    
    # Create record in Odoo (quality.check หรือ custom model)
    result = proxy.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'quality.check', 'create',
        [odoo_values]
    )
    
    # ถ้ามี measurements detail แยกเก็บ
    if data.measurements:
        for measurement in data.measurements:
            proxy.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'quality.check.line', 'create',
                [{
                    'check_id': result,
                    'parameter': measurement.get('parameter'),
                    'value': measurement.get('value'),
                    'spec_min': measurement.get('spec_min'),
                    'spec_max': measurement.get('spec_max'),
                    'result': measurement.get('result'),
                }]
            )
    
    return {"status": "success", "odoo_id": result}
```

---

## 5. When to Add Middleware (สัญญาณที่ควรเพิ่ม)

- [ ] ต้อง connect กับ 3+ systems พร้อมกัน
- [ ] Payload format เปลี่ยนบ่อย
- [ ] ต้องมี data validation ที่ซับซ้อน
- [ ] ต้องทำ rate limiting / throttling
- [ ] ต้องมี retry logic เมื่อ Odoo ล่ม
- [ ] ต้อง aggregate data จากหลาย sources ก่อนส่ง
- [ ] ต้องมี monitoring/dashboard แยก

---

## 6. Middleware Options

| Tool | Use Case | Learning Curve |
|------|----------|----------------|
| **n8n** | General workflow automation | ต่ำ (UI-based) |
| **Node-RED** | IoT / Industrial integration | ต่ำ-กลาง |
| **Apache Camel** | Enterprise integration | สูง |
| **Kong/Apigee** | API Gateway + transformation | กลาง-สูง |
| **Custom (Python/Node)** | Full control | ขึ้นกับทีม |

---

## 7. Security Considerations

```python
# ✅ ควรทำ:

# 1. Authentication
@app.post("/webhook/production")
async def production_webhook(
    data: ProductionData,
    x_api_key: str = Header(...)
):
    if x_api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# 2. Rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/webhook/production")
@limiter.limit("100/minute")
async def production_webhook(...):
    ...

# 3. Input validation (ใช้ Pydantic)
class ProductionData(BaseModel):
    quantity: int = Field(gt=0, le=10000)  # ต้อง > 0 และ <= 10000
    product_code: str = Field(min_length=1, max_length=50)

# 4. Logging
import logging
logger = logging.getLogger(__name__)

@app.post("/webhook/production")
async def production_webhook(data: ProductionData):
    logger.info(f"Received production data: {data.dict()}")
    ...
```

---

## 8. Next Steps

1. **กำหนด Odoo Models** ที่จะใช้ (mrp.workorder, quality.check หรือ custom models)
2. **สร้าง API User** ใน Odoo พร้อม permission ที่เหมาะสม
3. **พัฒนา Webhook Server** (FastAPI แนะนำ)
4. **ทดสอบกับข้อมูลตัวอย่าง** จากเครื่องจักรจริง
5. **Deploy** (Docker + Kubernetes / Cloud Run / EC2)
6. **Monitor** (logging, alerting, metrics)

---

## Resources

- [Odoo External API Documentation](https://www.odoo.com/documentation/16.0/developer/reference/external/external_api.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [n8n Self-hosting](https://docs.n8n.io/hosting/)

---

*Document created: 2026-02-27*
*Author: OC Claude LINE Bot Team*
