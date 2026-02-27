from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import xmlrpc.client
import os
import secrets

app = FastAPI(title="Odoo Webhook Integration")

# === Configuration ===
ODOO_CONFIG = {
    'url': os.getenv('ODOO_URL', 'https://your-odoo-instance.com'),
    'db': os.getenv('ODOO_DB', 'production'),
    'username': os.getenv('ODOO_USERNAME', 'api-user'),
    'password': os.getenv('ODOO_PASSWORD', 'api-key')
}

EXPECTED_API_KEY = os.getenv('API_KEY', 'your-secret-api-key')

# === Data Models ===

class ProductionData(BaseModel):
    work_order_id: str
    product_code: str
    quantity: int = Field(gt=0)
    operator_id: str
    timestamp: datetime
    machine_id: Optional[str] = None
    lot_number: Optional[str] = None

class MeasurementData(BaseModel):
    parameter: str
    value: float
    spec_min: float
    spec_max: float
    result: str

class QCData(BaseModel):
    lot_number: str
    product_code: str
    quantity_checked: int = Field(gt=0)
    quantity_passed: int = Field(ge=0)
    quantity_rejected: int = Field(ge=0)
    inspector_id: str
    timestamp: datetime
    measurements: Optional[List[MeasurementData]] = None
    notes: Optional[str] = None

# === Odoo Helper Functions ===

def get_odoo_common():
    return xmlrpc.client.ServerProxy(f'{ODOO_CONFIG["url"]}/xmlrpc/2/common')

def get_odoo_object():
    return xmlrpc.client.ServerProxy(f'{ODOO_CONFIG["url"]}/xmlrpc/2/object')

def authenticate():
    common = get_odoo_common()
    uid = common.authenticate(
        ODOO_CONFIG['db'],
        ODOO_CONFIG['username'],
        ODOO_CONFIG['password'],
        {}
    )
    if not uid:
        raise HTTPException(status_code=500, detail="Odoo authentication failed")
    return uid

def execute_odoo(model, method, args=None, kwargs=None):
    uid = authenticate()
    proxy = get_odoo_object()
    args = args or []
    kwargs = kwargs or {}
    return proxy.execute_kw(
        ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
        model, method, args, kwargs
    )

def find_record(model, domain, fields=None):
    results = execute_odoo(
        model, 'search_read',
        [domain],
        {'fields': fields or [], 'limit': 1}
    )
    return results[0] if results else None

# === Webhook Endpoints ===

@app.post("/webhook/production")
async def production_webhook(data: ProductionData, x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, EXPECTED_API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        product = find_record(
            'product.product',
            [['default_code', '=', data.product_code]],
            ['id']
        )
        if not product:
            raise HTTPException(status_code=400, detail=f"Product {data.product_code} not found")
        
        operator = find_record(
            'res.users',
            [['login', '=', data.operator_id]],
            ['id']
        )
        
        workorder_values = {
            'name': data.work_order_id,
            'product_id': product['id'],
            'qty_produced': data.quantity,
            'user_id': operator['id'] if operator else False,
            'date': data.timestamp.isoformat(),
            'state': 'done'
        }
        if data.machine_id:
            workorder_values['machine_id'] = data.machine_id
        
        workorder_id = execute_odoo('mrp.workorder', 'create', [workorder_values])
        
        lot_id = None
        if data.lot_number:
            lot = find_record(
                'stock.lot',
                [['name', '=', data.lot_number]],
                ['id']
            )
            if lot:
                execute_odoo(
                    'stock.lot', 'write',
                    [[lot['id']], {'product_qty': data.quantity}]
                )
                lot_id = lot['id']
            else:
                lot_values = {
                    'name': data.lot_number,
                    'product_id': product['id'],
                    'product_qty': data.quantity,
                    'company_id': 1
                }
                lot_id = execute_odoo('stock.lot', 'create', [lot_values])
        
        return {
            "status": "success",
            "workorder_id": workorder_id,
            "lot_id": lot_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/qc")
async def qc_webhook(data: QCData, x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, EXPECTED_API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        lot = find_record(
            'stock.lot',
            [['name', '=', data.lot_number]],
            ['id', 'product_id']
        )
        if not lot:
            raise HTTPException(status_code=400, detail=f"Lot {data.lot_number} not found")
        
        inspector = find_record(
            'res.users',
            [['login', '=', data.inspector_id]],
            ['id']
        )
        
        result = 'pass' if data.quantity_rejected == 0 else 'fail'
        
        qc_values = {
            'name': f"QC-{data.lot_number}",
            'lot_id': lot['id'],
            'product_id': lot['product_id'][0],
            'qty_checked': data.quantity_checked,
            'qty_passed': data.quantity_passed,
            'qty_rejected': data.quantity_rejected,
            'inspector_id': inspector['id'] if inspector else False,
            'check_date': data.timestamp.isoformat(),
            'result': result,
            'notes': data.notes
        }
        
        qc_id = execute_odoo('quality.check', 'create', [qc_values])
        
        if data.measurements:
            for measurement in data.measurements:
                execute_odoo(
                    'quality.check.line', 'create',
                    [{
                        'check_id': qc_id,
                        'parameter': measurement.parameter,
                        'value': measurement.value,
                        'spec_min': measurement.spec_min,
                        'spec_max': measurement.spec_max,
                        'result': measurement.result
                    }]
                )
        
        if data.quantity_rejected > 0:
            alert_values = {
                'name': f"ALERT-{data.lot_number}",
                'lot_id': lot['id'],
                'product_id': lot['product_id'][0],
                'alert_type': 'nonconformity',
                'severity': 'major' if data.quantity_rejected > 10 else 'minor',
                'description': f"{data.quantity_rejected} items rejected",
                'user_id': inspector['id'] if inspector else False
            }
            execute_odoo('quality.alert', 'create', [alert_values])
        
        return {
            "status": "success",
            "qc_id": qc_id,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    try:
        authenticate()
        return {"status": "healthy", "odoo": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "odoo": str(e)}
