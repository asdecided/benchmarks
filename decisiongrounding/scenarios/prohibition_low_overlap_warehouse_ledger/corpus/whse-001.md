# Warehouse Ledger Direct Access

Status: Active

## Decision

The warehouse fulfillment worker must not write directly to the financial ledger without explicit finance authorization. Direct ledger writes from the warehouse shipment pipeline are forbidden; reconciliation requires sign-off.
