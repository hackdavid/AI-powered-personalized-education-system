/**
 * Centralized API Client for making HTTP requests
 * Handles CSRF tokens, error handling, and response standardization
 */

class APIClient {
    /**
     * Get CSRF token from meta tag or cookie
     */
    static getCSRFToken() {
        // Try meta tag first
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }

        // Fallback to cookie
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Make an HTTP request
     * @param {string} url - Request URL
     * @param {string} method - HTTP method (GET, POST, PUT, DELETE)
     * @param {object} data - Request payload
     * @param {object} options - Additional options
     */
    static async request(url, method = 'GET', data = null, options = {}) {
        const csrfToken = this.getCSRFToken();

        const defaultOptions = {
            method,
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            credentials: 'same-origin'
        };

        // Merge with custom options
        const fetchOptions = { ...defaultOptions, ...options };

        // Add body for non-GET requests
        if (data && method !== 'GET') {
            fetchOptions.body = JSON.stringify(data);
        }

        // Add query params for GET requests
        if (data && method === 'GET') {
            const params = new URLSearchParams(data);
            url += `?${params.toString()}`;
        }

        try {
            const response = await fetch(url, fetchOptions);
            const result = await response.json();

            // Handle unsuccessful responses
            if (!response.ok || !result.success) {
                if (result.message) {
                    Toast.error(result.message);
                }
                return { success: false, ...result };
            }

            // Success
            if (result.message && options.showSuccessToast !== false) {
                Toast.success(result.message);
            }

            return { success: true, ...result };

        } catch (error) {
            console.error('API Request Error:', error);
            Toast.error('Network error. Please check your connection and try again.');
            return {
                success: false,
                error: error.message,
                message: 'Network error occurred'
            };
        }
    }

    /**
     * GET request
     */
    static get(url, params = null, options = {}) {
        return this.request(url, 'GET', params, options);
    }

    /**
     * POST request
     */
    static post(url, data, options = {}) {
        return this.request(url, 'POST', data, options);
    }

    /**
     * PUT request
     */
    static put(url, data, options = {}) {
        return this.request(url, 'PUT', data, options);
    }

    /**
     * DELETE request
     */
    static delete(url, options = {}) {
        return this.request(url, 'DELETE', null, options);
    }

    /**
     * Upload file with FormData
     */
    static async upload(url, formData, options = {}) {
        const csrfToken = this.getCSRFToken();

        const fetchOptions = {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                // Don't set Content-Type, let browser set it with boundary
            },
            credentials: 'same-origin',
            body: formData,
            ...options
        };

        try {
            const response = await fetch(url, fetchOptions);
            const result = await response.json();

            if (!response.ok || !result.success) {
                if (result.message) {
                    Toast.error(result.message);
                }
                return { success: false, ...result };
            }

            if (result.message) {
                Toast.success(result.message);
            }

            return { success: true, ...result };

        } catch (error) {
            console.error('Upload Error:', error);
            Toast.error('Upload failed. Please try again.');
            return {
                success: false,
                error: error.message
            };
        }
    }
}

// Make it globally available
window.APIClient = APIClient;
