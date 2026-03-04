const API_BASE = '/api';

async function call(path, method = 'GET', body = null) {
  const basePath = `${API_BASE}${path}`;
  let response = await fetch(basePath, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null
  });

  // Some servers/middlewares differentiate trailing slash and can return 405.
  // Retry once with slash-variant path for resilience.
  if (response.status === 405) {
    const altPath = basePath.endsWith('/') ? basePath.slice(0, -1) : `${basePath}/`;
    response = await fetch(altPath, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : null
    });
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error ${response.status} (${basePath})`);
  }
  return response.json();
}

export async function getRecommendations(payload) {
  return call('/recommend', 'POST', payload);
}

export async function createPaymentIntent(payload) {
  return call('/checkout/intent', 'POST', payload);
}

export async function completePayment(payload) {
  return call('/checkout/complete', 'POST', payload);
}
