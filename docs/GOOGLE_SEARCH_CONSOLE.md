# Google Search Console setup

The frontend build supports Search Console verification and generates a sitemap/robots file from the actual public storefront URL.

## Amplify build environment

Set these variables for the frontend build:

- `VITE_SITE_URL`: the canonical public storefront origin, for example `https://shop.example.com`. Use the real customer-facing storefront domain, not the API hostname.
- `VITE_GOOGLE_SITE_VERIFICATION`: optional HTML-tag verification token copied from the Search Console property.

The build generates `sitemap.xml` and `robots.txt` in the Vite output directory. If `VITE_SITE_URL` is missing, generation is skipped with a warning rather than publishing an incorrect sitemap. Invalid non-HTTP(S) URLs fail the build.

## Search Console

1. Add the matching Domain property in Google Search Console (recommended) or a URL-prefix property.
2. For Domain property verification, add Google's exact DNS TXT record at the domain's DNS provider. DNS changes are outside this repository and must be performed by the domain owner.
3. Alternatively, for URL-prefix verification, set `VITE_GOOGLE_SITE_VERIFICATION` to the exact token from Google's HTML-tag method and rebuild.
4. Deploy the frontend build, verify the property, then submit `https://YOUR-STOREFRONT-DOMAIN/sitemap.xml` in Search Console.
5. Confirm that `/robots.txt` and `/sitemap.xml` return HTTP 200 on the public domain.

## Sitemap scope

The initial sitemap contains the storefront home, deals, and published static information/legal pages. It excludes admin, account, checkout, login, registration and wishlist routes. Product/category URLs are not included yet because they are dynamic catalogue data and should be generated from verified public API records in a follow-up once canonical product URLs are confirmed.

## Important

Do not use the API hostname as the storefront canonical URL. Do not commit Google's verification token to source control; set it only in the Amplify environment. DNS TXT verification is preferred because it does not require storing a token in the frontend build.
