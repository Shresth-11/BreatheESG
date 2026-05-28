import axios from 'axios';

let BASE = process.env.REACT_APP_API_URL || 'https://breathe-esg-api-naso.onrender.com/api';
if (BASE && !BASE.endsWith('/api') && !BASE.endsWith('/api/')) {
  BASE = BASE.replace(/\/$/, '') + '/api';
}

const api = axios.create({ baseURL: BASE, withCredentials: true });

export const getTenants = () => api.get('/tenants/');
export const getBatches = (tenantId) => api.get(`/batches/?tenant=${tenantId}`);
export const getRecords = (params) => api.get('/records/', { params });
export const getRecord = (id) => api.get(`/records/${id}/`);
export const getSummary = (tenantId) => api.get('/records/summary/', { params: { tenant: tenantId } });
export const approveRecord = (id, note) => api.post(`/records/${id}/approve/`, { note });
export const flagRecord = (id, reason) => api.post(`/records/${id}/flag/`, { reason });
export const lockRecord = (id) => api.post(`/records/${id}/lock/`);
export const ingestFile = (formData) => api.post('/ingest/', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
});
