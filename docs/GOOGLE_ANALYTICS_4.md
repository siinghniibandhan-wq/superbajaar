# Google Analytics 4 setup

The storefront integration is optional and disabled by default.

## Configure

1. Create or select a GA4 web data stream for the public Super Bajaar storefront.
2. Copy its Measurement ID (format: `G-XXXXXXXXXX`).
3. Add `VITE_GA4_MEASUREMENT_ID` to the Amplify frontend build environment.
4. Trigger a fresh Amplify build after the variable is saved.

Do not put service-account credentials, API secrets, customer identifiers, names, email addresses, phone numbers, delivery PINs, or addresses in frontend analytics configuration or event payloads.

## Consent and scope

- The GA4 script is not loaded until a visitor chooses **Allow analytics**.
- Declining analytics keeps the script disabled.
- Tracking runs only on the public storefront, not the `/admin` console.
- The consent choice is stored locally in the visitor's browser.
- No analytics request is sent when the Measurement ID is missing.

## Events

- `page_view`: storefront route changes.
- `view_item`: product detail route viewed.
- `add_to_cart`: item added to basket.
- `begin_checkout`: checkout submitted.
- `order_placed`: order API accepted a website order.

`order_placed` is intentionally not named `purchase`: the current checkout flow reports that online payment is not enabled, so order creation alone must not be misreported as a completed/paid purchase. Add the GA4 `purchase` event only after a trusted payment/order-confirmation state is available.

## Verification

After configuration and consent, use GA4 Realtime/DebugView to confirm page views and ecommerce events. Test both consent choices and confirm that no Google Analytics script/network request occurs before consent or after decline.
