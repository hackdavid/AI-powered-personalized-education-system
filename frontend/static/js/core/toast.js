/**
 * Toast Notification System
 * Provides user feedback with temporary toast messages
 */

class Toast {
    /**
     * Show a toast notification
     * @param {string} message - Message to display
     * @param {string} type - Toast type (success, error, info, warning)
     * @param {number} duration - Duration in milliseconds
     */
    static show(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container');
        if (!container) {
            console.error('Toast container not found');
            return;
        }

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        // Icon based on type
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ⓘ'
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;

        // Add to container
        container.appendChild(toast);

        // Animate in
        setTimeout(() => toast.classList.add('show'), 10);

        // Auto-remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    /**
     * Show success toast
     */
    static success(message, duration = 3000) {
        this.show(message, 'success', duration);
    }

    /**
     * Show error toast
     */
    static error(message, duration = 5000) {
        this.show(message, 'error', duration);
    }

    /**
     * Show info toast
     */
    static info(message, duration = 3000) {
        this.show(message, 'info', duration);
    }

    /**
     * Show warning toast
     */
    static warning(message, duration = 4000) {
        this.show(message, 'warning', duration);
    }

    /**
     * Show loading toast (doesn't auto-dismiss)
     */
    static loading(message) {
        const container = document.getElementById('toast-container');
        if (!container) return null;

        const toast = document.createElement('div');
        toast.className = 'toast toast-loading';
        toast.innerHTML = `
            <span class="toast-spinner"></span>
            <span class="toast-message">${message}</span>
        `;

        container.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 10);

        // Return toast element so it can be dismissed manually
        return toast;
    }

    /**
     * Dismiss a specific toast
     */
    static dismiss(toast) {
        if (toast) {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }
    }
}

// Make it globally available
window.Toast = Toast;
