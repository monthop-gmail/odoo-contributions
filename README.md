# Odoo Contributions

Collection of Odoo integrations, webhooks, and custom modules.

## Projects

### 1. Webhook Middleware

FastAPI-based webhook server for integrating production and QC systems with Odoo.

**Features:**
- Production webhook (`POST /webhook/production`)
- QC webhook (`POST /webhook/qc`)
- Direct Odoo XML-RPC integration
- API key authentication
- Input validation with Pydantic

**Documentation:**
- [Webhook Integration Guide](docs/webhook-middleware-guide.md)

## Structure

```
odoo-contributions/
├── README.md
├── webhook-middleware/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
└── docs/
    └── webhook-middleware-guide.md
```

## License

Private - All rights reserved
