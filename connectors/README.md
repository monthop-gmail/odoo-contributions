# Connectors

2-way sync connectors ระหว่าง Odoo และระบบภายนอก

## Projects

- LINE Bot Connector — (coming soon)
- WooCommerce Connector — (coming soon)
- SAP Connector — (coming soon)

## Structure

แต่ละ connector ควรมี:

```
connector-name/
├── README.md
├── main.py (หรือ connector.py)
├── requirements.txt
├── Dockerfile
└── config.example.env
```
