-- Product reviews are moderated before they become public.
CREATE TABLE IF NOT EXISTS product_reviews (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  reviewer_name TEXT NOT NULL CHECK (length(trim(reviewer_name)) BETWEEN 1 AND 80),
  rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review_text TEXT NOT NULL CHECK (length(trim(review_text)) BETWEEN 3 AND 2000),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  moderated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_product_reviews_public
  ON product_reviews(product_id, status, created_at DESC);
