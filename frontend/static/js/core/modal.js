/**
 * Modal Manager for handling popups and dialogs
 * Provides reusable modal functionality
 */

class Modal {
    /**
     * Show a modal
     * @param {string} modalId - ID of the modal element
     */
    static show(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('show');
            document.body.classList.add('modal-open');
        }
    }

    /**
     * Hide a modal
     * @param {string} modalId - ID of the modal element
     */
    static hide(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('show');
            document.body.classList.remove('modal-open');
        }
    }

    /**
     * Toggle a modal
     * @param {string} modalId - ID of the modal element
     */
    static toggle(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            if (modal.classList.contains('show')) {
                this.hide(modalId);
            } else {
                this.show(modalId);
            }
        }
    }

    /**
     * Create and show a confirmation dialog
     * @param {object} options - Dialog options
     */
    static confirm(options = {}) {
        return new Promise((resolve) => {
            const {
                title = 'Confirm Action',
                message = 'Are you sure?',
                confirmText = 'Confirm',
                cancelText = 'Cancel',
                confirmClass = 'btn-primary',
                cancelClass = 'btn-secondary'
            } = options;

            // Create modal HTML
            const modalId = 'confirm-modal-' + Date.now();
            const modalHTML = `
                <div id="${modalId}" class="modal show">
                    <div class="modal-overlay"></div>
                    <div class="modal-dialog">
                        <div class="modal-header">
                            <h3>${title}</h3>
                        </div>
                        <div class="modal-body">
                            <p>${message}</p>
                        </div>
                        <div class="modal-footer">
                            <button class="btn ${cancelClass}" data-action="cancel">${cancelText}</button>
                            <button class="btn ${confirmClass}" data-action="confirm">${confirmText}</button>
                        </div>
                    </div>
                </div>
            `;

            // Add to document
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            document.body.classList.add('modal-open');

            const modal = document.getElementById(modalId);

            // Handle button clicks
            modal.addEventListener('click', (e) => {
                if (e.target.dataset.action === 'confirm') {
                    modal.remove();
                    document.body.classList.remove('modal-open');
                    resolve(true);
                } else if (e.target.dataset.action === 'cancel' || e.target.classList.contains('modal-overlay')) {
                    modal.remove();
                    document.body.classList.remove('modal-open');
                    resolve(false);
                }
            });
        });
    }

    /**
     * Show an alert dialog
     * @param {string} message - Alert message
     * @param {string} title - Alert title
     */
    static alert(message, title = 'Alert') {
        return this.confirm({
            title,
            message,
            confirmText: 'OK',
            cancelText: '',
            confirmClass: 'btn-primary'
        });
    }

    /**
     * Load content into a modal via AJAX
     * @param {string} modalId - ID of the modal element
     * @param {string} url - URL to load content from
     */
    static async loadContent(modalId, url) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const contentContainer = modal.querySelector('.modal-body');
        if (!contentContainer) return;

        // Show loading state
        contentContainer.innerHTML = '<div class="loading">Loading...</div>';
        this.show(modalId);

        // Fetch content
        const result = await APIClient.get(url, null, { showSuccessToast: false });

        if (result.success && result.data && result.data.html) {
            contentContainer.innerHTML = result.data.html;
        } else {
            contentContainer.innerHTML = '<div class="error">Failed to load content</div>';
        }
    }

    /**
     * Initialize all modals on page
     */
    static initialize() {
        // Handle modal triggers
        document.addEventListener('click', (e) => {
            const trigger = e.target.closest('[data-modal-show]');
            if (trigger) {
                const modalId = trigger.dataset.modalShow;
                this.show(modalId);
            }

            const hide = e.target.closest('[data-modal-hide]');
            if (hide) {
                const modalId = hide.dataset.modalHide;
                this.hide(modalId);
            }

            // Close on overlay click
            if (e.target.classList.contains('modal-overlay')) {
                const modal = e.target.closest('.modal');
                if (modal) {
                    this.hide(modal.id);
                }
            }
        });

        // Close on ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const openModal = document.querySelector('.modal.show');
                if (openModal) {
                    this.hide(openModal.id);
                }
            }
        });
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    Modal.initialize();
});

// Make it globally available
window.Modal = Modal;
