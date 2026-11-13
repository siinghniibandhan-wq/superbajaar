# Product image storage and WebP uploads

## Why file uploads currently fail

The catalogue upload endpoint stores file bytes in S3 and saves the resulting CloudFront URL in `product_images`. It returns HTTP 503 when either `MEDIA_BUCKET` or `MEDIA_PUBLIC_BASE_URL` is missing. This is a backend storage configuration problem, not a browser file-picker problem.

The product image URL form is a separate workflow: it stores a supplied HTTP(S) URL and does not upload or convert the remote image.

## Provision the product media storage

The CloudFormation template `backend/infra/product-media-storage.yaml` creates:

- A dedicated S3 bucket with public access blocked and bucket-owner object ownership.
- A CloudFront distribution using Origin Access Control. Only CloudFront can read objects under `products/*`; the bucket is not public.
- A narrowly scoped `s3:PutObject` policy attached to the existing EC2 instance role running `superbajaar-backend.service`.

Before deployment, identify the exact IAM role attached to the backend EC2 instance in the EC2 console. Do not use an IAM user access key in the backend environment; boto3 should use the instance role.

From a trusted AWS CLI session in the correct account, deploy the stack in the backend region:

```bash
aws cloudformation deploy \
  --template-file backend/infra/product-media-storage.yaml \
  --stack-name superbajaar-product-media \
  --parameter-overrides BackendInstanceRoleName=<BACKEND_EC2_ROLE_NAME> \
  --capabilities CAPABILITY_IAM \
  --region ap-south-1
```

Retrieve the two values to configure on the backend:

```bash
aws cloudformation describe-stacks \
  --stack-name superbajaar-product-media \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region ap-south-1
```

In the backend environment file used by the running service (production checkout: `/opt/superbajaar/backend/.env`), set:

```dotenv
MEDIA_BUCKET=<MediaBucketName output>
MEDIA_PUBLIC_BASE_URL=<MediaPublicBaseUrl output>
AWS_REGION=ap-south-1
```

Keep the output URL as the CloudFront HTTPS URL. Do not make the S3 bucket public. Restart the backend service after setting the values:

```bash
sudo systemctl restart superbajaar-backend.service
sudo systemctl status superbajaar-backend.service --no-pager
```

Then upload a test product image from the Catalogue workspace and confirm that the returned image URL uses the CloudFront domain. Check the image in a private browser window as well as while signed in; delivery must not depend on an admin session.

## Image format and size behavior

Direct file uploads now use browser-native image conversion before reaching the API:

- JPEG and PNG are resized so the longest edge is at most 1,920 pixels and encoded as WebP at quality 0.82.
- Existing WebP uploads are kept as WebP without another lossy encode.
- GIF uploads are kept as GIF so their animation is not silently lost.
- The existing 10 MB upload limit is retained and checked for the selected and converted files.

This conversion applies to the direct file-upload control. Images entered as external URLs are saved as URL references and are not downloaded or converted; use the file-upload control when WebP conversion and hosting on the product media CDN are required. Existing image records are not rewritten.

## Operational and security notes

- The bucket is private; public image delivery is through CloudFront Origin Access Control.
- The EC2 role receives upload permission only for `products/*` in this dedicated bucket.
- The backend creates random object keys and sends the detected MIME type plus immutable cache headers.
- The template retains the bucket when the stack is deleted to protect uploaded product media. Back up or intentionally migrate that data before any manual bucket deletion.
- This stack provisions AWS resources and incurs S3 and CloudFront usage charges. Deploy it only in the intended AWS account and region.
