const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function fetchCatalogue() {
  const response = await fetch(API_BASE + '/api/products', { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Catalogue API returned ' + response.status);
  const payload = await response.json();
  if (!Array.isArray(payload.items)) throw new Error('Catalogue response format is invalid');
  return payload.items.map(item => ({
    id: Number(item.id), sku: item.sku, name: item.name, category: item.category,
    description: item.description || '', image: item.image_url || '/product-placeholder.svg',
    price: Number(item.price) || 0, mrp: Number(item.mrp) || Number(item.price) || 0,
    off: Number(item.mrp) > 0 ? Math.max(0, Math.round((1 - Number(item.price) / Number(item.mrp)) * 100)) : 0,
    tag: item.in_stock ? 'In stock' : 'Out of stock', rating: 0, reviews: 0,
    variants: Array.isArray(item.variants) && item.variants.length ? item.variants : ['Standard'],
    stockQuantity: Number(item.quantity) || 0
  }));
}
