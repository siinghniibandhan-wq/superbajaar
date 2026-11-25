-- Colour values created from the Product Create page were stored only as per-product custom options,
-- so the storefront could not find their HEX (blank swatch). Copy them onto the shared attribute.
UPDATE product_attributes pa
SET options = COALESCE(pa.options, '[]'::jsonb) || sub.missing
FROM (
  SELECT a.id,
         jsonb_agg(DISTINCT c.value) FILTER (WHERE jsonb_typeof(c.value) = 'object'
           AND NOT EXISTS (
             SELECT 1 FROM jsonb_array_elements(COALESCE(a.options, '[]'::jsonb)) o
             WHERE lower(CASE WHEN jsonb_typeof(o) = 'object' THEN o->>'name' ELSE o #>> '{}' END) = lower(c.value->>'name')
           )) AS missing
  FROM product_attributes a
  JOIN product_attribute_custom_options c ON c.attribute_id = a.id
  WHERE a.value_type = 'colour'
  GROUP BY a.id
) sub
WHERE pa.id = sub.id AND sub.missing IS NOT NULL;
