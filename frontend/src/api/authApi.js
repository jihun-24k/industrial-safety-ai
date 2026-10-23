import { request } from './client.js';

export const authApi = {
  signup(username, password) {
    return request('/auth-api/signup', {
      method: 'POST',
      body: new URLSearchParams({ username, password }),
    });
  },
  check() {
    return request('/auth-api/auth/check');
  },

  login(username, password) {
    return request('/auth-api/login', {
      method: 'POST',
      body: new URLSearchParams({ username, password }),
    });
  },

  logout() {
    return request('/auth-api/logout', { method: 'POST' });
  },
};
