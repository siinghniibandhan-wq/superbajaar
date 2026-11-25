-- Image values typed on the Product page were stored only as per-product custom options, so the storefront
-- (which reads value names from the shared attribute) could only show the image link for them.
-- Copy them onto the shared attribute, identified by image link (several values may share a name).
-- Additive and idempotent: existing shared values, variants and products are not changed.
UPDATE product_attributes pa
SET options = COALESCE(pa.options, '[]'::jsonb) || sub.missing
FROM (
  SELECT m.attribute_id AS id,
         jsonb_agg(jsonb_build_object('name', m.name, 'image', m.image) ORDER BY m.first_id) AS missing
  FROM (
    SELECT c.attribute_id,
           lower(btrim(c.value->>'image')) AS image_key,
           (array_agg(btrim(c.value->>'name') ORDER BY c.id))[1] AS name,
           (array_agg(btrim(c.value->>'image') ORDER BY c.id))[1] AS image,
           min(c.id) AS first_id
    FROM product_attribute_custom_options c
    JOIN product_attributes a ON a.id = c.attribute_id AND a.value_type = 'image'
    WHERE jsonb_typeof(c.value) = 'object'
      AND btrim(COALESCE(c.value->>'image', '')) <> ''
      AND btrim(COALESCE(c.value->>'name', '')) <> ''
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(a.options, '[]'::jsonb)) o
        WHERE lower(btrim(CASE WHEN jsonb_typeof(o) = 'object' THEN o->>'image' ELSE o #>> '{}' END)) = lower(btrim(c.value->>'image'))
      )
    GROUP BY c.attribute_id, lower(btrim(c.value->>'image'))
  ) m
  GROUP BY m.attribute_id
) sub
WHERE pa.id = sub.id AND sub.missing IS NOT NULL;
