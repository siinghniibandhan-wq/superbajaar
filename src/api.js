const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
async function request(path, { token, ...options } = {}) {
 const response = await fetch(API_BASE + path, { ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(options.headers || {}) } });
 const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || 'Request failed (' + response.status + ')'); return payload;
}
export async function fetchCatalogue() { const payload = await request('/api/products'); if (!Array.isArray(payload.items)) throw new Error('Catalogue response format is invalid'); return payload.items.map(item => ({ id:Number(item.id),sku:item.sku,name:item.name,category:item.category,description:item.description||'',image:item.image_url||'/product-placeholder.svg',price:Number(item.price)||0,mrp:Number(item.mrp)||Number(item.price)||0,off:Number(item.mrp)>0?Math.max(0,Math.round((1-Number(item.price)/Number(item.mrp))*100)):0,tag:item.in_stock?'In stock':'Out of stock',rating:0,reviews:0,variants:Array.isArray(item.variants)&&item.variants.length?item.variants:['Standard'],stockQuantity:Number(item.quantity)||0 })); }
export const signIn=(email,password)=>request('/api/auth/login',{method:'POST',body:JSON.stringify({email,password})});
export const signUp=(name,email,phone,password)=>request('/api/auth/register',{method:'POST',body:JSON.stringify({name,email,phone,password})});
export const fetchCurrentUser=token=>request('/api/auth/me',{token});
export const submitOrder=(token,cart,address,coupon)=>request('/api/orders',{token,method:'POST',body:JSON.stringify({items:cart.map(item=>({product_id:Number(item.id),variant:item.variant||'Standard',quantity:Number(item.qty)})),address,coupon:coupon||''})});
export const fetchOrders=token=>request('/api/orders',{token});
export const submitTicket=(token,topic,message)=>request('/api/support',{token,method:'POST',body:JSON.stringify({topic,message})});
