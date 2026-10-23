import { request } from './client';

export const authApi = {
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
