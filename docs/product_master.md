# Product Master Requirements

A product is a catalogue identity; a sellable variant/SKU is a specific purchasable unit. A product can have multiple variants, each with its own SKU, barcode, images, price rules and inventory.

## Product fields
- Stable internal ID and optional source-system ID
- Name, description, brand, category, status, product type
- Attributes and variant definitions
- Tax classification/HSN where applicable and configurable tax treatment
- Unit of measure, dimensions and shipping attributes where relevant
- Main image, gallery, SEO fields and website publication status

## Variant/SKU fields
- Unique SKU, optional barcode, attribute values
- Variant-specific images
- MRP and selling-price configuration, currency and effective dates
- Supplier references and supplier-specific purchase terms
- Stock tracking, batch/lot/expiry requirements
- Weight/dimensions and active status

Do not store secrets in product records. Price history should be append-only/auditable and reflect verified changes, not manually invented prior prices. Regional availability must be computed server-side from stock, serviceability, fulfilment rules and status.
