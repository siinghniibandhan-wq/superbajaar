# Migration Templates

These CSV files define import headers only; they contain no real supplier, customer, stock, or order data.

## Import order
1. categories.csv
2. products.csv
3. product_variants.csv
4. warehouses.csv
5. suppliers.csv
6. supplier_products.csv
7. opening_stock.csv
8. price_history.csv
9. customers.csv
10. historical_orders.csv

Validate references, duplicates, tax fields, units, quantities, and totals before import. Keep a source-system ID for traceability. Never fabricate historical prices or opening balances. Opening stock must be reconciled with a dated physical/system stock count and valuation before posting.

## Additional templates
Create purchase order and purchase order line templates when the purchase module is implemented. Do not commit real business records or credentials to Git.
