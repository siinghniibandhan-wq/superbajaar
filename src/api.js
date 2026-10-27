// Accept either an origin or an origin already ending in /api.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '').replace(/\/api$/i, '');
async function request(path, { token, ...options } = {}) {
 const response = await fetch(API_BASE + path, { ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(options.headers || {}) } });
 const payload = await response.json().catch(() => ({})); if (!response.ok) { const detail = payload?.detail ?? payload?.message ?? payload?.error; const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => typeof item === 'string' ? item : item?.msg || JSON.stringify(item)).join('; ') : detail && typeof detail === 'object' ? (detail.message || detail.msg || JSON.stringify(detail)) : 'Request failed (' + response.status + ')'; throw new Error(message); } return payload;
}
export async function fetchCatalogue() {
 const limit=200; let offset=0; let total=Infinity; const records=[];
 while(offset<total) {
  const payload=await request('/api/products?limit='+limit+'&offset='+offset);
  if(!Array.isArray(payload.items)) throw new Error('Catalogue response format is invalid');
  records.push(...payload.items);
  total=Number.isFinite(Number(payload.total))?Number(payload.total):offset+payload.items.length;
  if(!payload.items.length) break;
  offset+=payload.items.length;
 }
 return records.map(item => ({ id:Number(item.id),sku:item.sku,name:item.name,category:item.category,description:item.description||'',image:item.image_url||'/product-placeholder.svg',price:Number(item.price)||0,mrp:Number(item.mrp)||Number(item.price)||0,off:Number(item.mrp)>0?Math.max(0,Math.round((1-Number(item.price)/Number(item.mrp))*100)):0,tag:item.in_stock?'In stock':'Out of stock',rating:0,reviews:0,variants:Array.isArray(item.variants)&&item.variants.length?item.variants:['Standard'],stockQuantity:Number(item.quantity)||0 }));
}
export const signIn=(email,password)=>request('/api/auth/login',{method:'POST',body:JSON.stringify({email,password})});
export const signUp=(name,email,phone,password)=>request('/api/auth/register',{method:'POST',body:JSON.stringify({name,email,phone,password})});
export const fetchCurrentUser=token=>request('/api/auth/me',{token});
export const submitOrder=(token,cart,address,coupon)=>request('/api/orders',{token,method:'POST',body:JSON.stringify({items:cart.map(item=>({product_id:Number(item.id),variant:item.variant||'Standard',quantity:Number(item.qty)})),address,coupon:coupon||''})});
export const fetchOrders=token=>request('/api/orders',{token});
export const cancelOrder=(token,code)=>request('/api/orders/'+encodeURIComponent(code)+'/cancel',{token,method:'PATCH'});
export const submitTicket=(token,topic,message)=>request('/api/support',{token,method:'POST',body:JSON.stringify({topic,message})});

export const createAdminProduct = (token, product) => request('/api/admin/products', { token, method: 'POST', body: JSON.stringify(product) });
export const fetchAdminOrders = token => request('/api/admin/orders', { token });
export const updateAdminOrderStatus = (token, code, status) => request('/api/admin/orders/' + encodeURIComponent(code) + '/status', { token, method: 'PATCH', body: JSON.stringify({ status }) });

export const updateAdminStock = (token, id, quantity) => request('/api/admin/products/' + Number(id) + '/stock', { token, method: 'PATCH', body: JSON.stringify({ quantity }) });

export const fetchPriceHistory = (id, days = 30) => request('/api/products/' + Number(id) + '/price-history?days=' + Number(days));

export const fetchAdminSupport = token => request('/api/admin/support', { token });
export const updateAdminSupportStatus = (token, id, status) => request('/api/admin/support/' + Number(id) + '/status', { token, method: 'PATCH', body: JSON.stringify({ status }) });

export const updateAdminProduct = (token, id, product) => request('/api/admin/products/' + Number(id), { token, method: 'PATCH', body: JSON.stringify(product) });
export const checkDeliveryAvailability = pin => request('/api/delivery/availability?pin=' + encodeURIComponent(pin));
