# Odoo Contributions

Collection of Odoo integrations, webhooks, and custom modules.

## 📁 Projects

### Webhooks

| Project | Description | Status |
|---------|-------------|--------|
| [Production & QC](webhooks/production-qc/) | Webhook สำหรับรับ Production และ QC Records | ✅ Ready |
| E-commerce | Webhook จาก Shopee/Lazada/TikTok | 📝 Planned |

### Connectors

| Project | Description | Status |
|---------|-------------|--------|
| LINE Bot | LINE Bot connector สำหรับ Odoo | 📝 Planned |
| WooCommerce | 2-way sync กับ WooCommerce | 📝 Planned |

### Custom Modules

| Project | Description | Status |
|---------|-------------|--------|
| Thai Localization | ฟีเจอร์เฉพาะประเทศไทย | 📝 Planned |
| Marketplace v18 | Multi-vendor marketplace | 📝 Planned |

### Scripts

| Project | Description | Status |
|---------|-------------|--------|
| Data Migration | Scripts ย้ายข้อมูล | 📝 Planned |
| Bulk Import | นำเข้าข้อมูลจำนวนมาก | 📝 Planned |

## 📚 Documentation

- [Documentation Index](docs/index.md)
- [Webhook Middleware Guide](docs/webhook-middleware-guide.md)

## 🚀 Quick Start

### Running a Webhook

```bash
cd webhooks/production-qc
docker build -t odoo-webhook .
docker run -p 8000:8000 \
  -e ODOO_URL=https://your-odoo.com \
  -e ODOO_DB=production \
  -e ODOO_USERNAME=api-user \
  -e ODOO_PASSWORD=api-key \
  -e API_KEY=your-secret-key \
  odoo-webhook
```

## 🏗️ Project Structure

```
odoo-contributions/
├── webhooks/           # Webhook integrations (external -> Odoo)
├── connectors/         # 2-way sync connectors
├── custom-modules/     # Odoo custom modules
├── scripts/            # Utility scripts
├── templates/          # Project templates
└── docs/               # Documentation
```

## 📝 Adding a New Project

1. เลือก category ที่เหมาะสม (webhooks/connectors/custom-modules/scripts)
2. สร้าง folder ใหม่พร้อมโครงสร้างพื้นฐาน
3. เพิ่ม README.md และ documentation
4. Create PR

## License

Private - All rights reserved
