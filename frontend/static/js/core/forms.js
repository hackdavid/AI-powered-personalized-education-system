/**
 * Form Handler for dynamic form submission and validation
 * Simplifies form handling with loading states and error display
 */

class FormHandler {
    /**
     * Submit a form via AJAX
     * @param {HTMLFormElement} formElement - The form to submit
     * @param {object} options - Configuration options
     */
    static async submit(formElement, options = {}) {
        // Prevent default form submission
        if (options.event) {
            options.event.preventDefault();
        }

        // Extract form data
        const formData = new FormData(formElement);
        const data = Object.fromEntries(formData);

        // Get URL and method
        const url = options.url || formElement.action;
        const method = options.method || formElement.method.toUpperCase();

        // Find submit button
        const submitBtn = formElement.querySelector('[type="submit"]');
        const originalText = submitBtn ? submitBtn.textContent : '';

        // Show loading state
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = options.loadingText || 'Loading...';
        }

        // Clear previous errors
        this.clearErrors(formElement);

        // Make request
        const result = await APIClient.request(url, method, data, {
            showSuccessToast: options.showSuccessToast !== false
        });

        // Restore button state
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }

        // Handle response
        if (result.success) {
            // Reset form if specified
            if (options.resetOnSuccess) {
                formElement.reset();
            }

            // Execute success callback
            if (options.onSuccess) {
                options.onSuccess(result);
            }
        } else {
            // Display field errors
            if (result.errors) {
                this.displayErrors(formElement, result.errors);
            }

            // Execute error callback
            if (options.onError) {
                options.onError(result);
            }
        }

        return result;
    }

    /**
     * Display validation errors on form fields
     */
    static displayErrors(formElement, errors) {
        Object.keys(errors).forEach(fieldName => {
            const field = formElement.querySelector(`[name="${fieldName}"]`);
            if (field) {
                const errorContainer = this.getOrCreateErrorContainer(field);
                errorContainer.textContent = errors[fieldName];
                field.classList.add('error');
            }
        });
    }

    /**
     * Clear all form errors
     */
    static clearErrors(formElement) {
        formElement.querySelectorAll('.error').forEach(field => {
            field.classList.remove('error');
        });
        formElement.querySelectorAll('.field-error').forEach(error => {
            error.textContent = '';
        });
    }

    /**
     * Get or create error container for a field
     */
    static getOrCreateErrorContainer(field) {
        let errorContainer = field.parentElement.querySelector('.field-error');
        if (!errorContainer) {
            errorContainer = document.createElement('div');
            errorContainer.className = 'field-error';
            field.parentElement.appendChild(errorContainer);
        }
        return errorContainer;
    }

    /**
     * Initialize a form with auto-submit
     */
    static initialize(formElement, options = {}) {
        formElement.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.submit(formElement, { ...options, event: e });
        });
    }

    /**
     * Dynamic formset management (Django formsets)
     */
    static initFormset(formsetPrefix, options = {}) {
        const addButton = document.querySelector(`[data-formset-add="${formsetPrefix}"]`);
        const container = document.querySelector(`[data-formset-container="${formsetPrefix}"]`);
        const template = document.querySelector(`[data-formset-template="${formsetPrefix}"]`);
        const totalFormsInput = document.querySelector(`#id_${formsetPrefix}-TOTAL_FORMS`);

        if (!addButton || !container || !template || !totalFormsInput) {
            console.error('Formset elements not found');
            return;
        }

        let formCount = parseInt(totalFormsInput.value);

        // Add form
        addButton.addEventListener('click', () => {
            const newForm = template.innerHTML.replace(/__prefix__/g, formCount);
            container.insertAdjacentHTML('beforeend', newForm);
            formCount++;
            totalFormsInput.value = formCount;

            // Execute callback if provided
            if (options.onAdd) {
                options.onAdd(formCount - 1);
            }
        });

        // Delete form (delegate event)
        container.addEventListener('click', (e) => {
            if (e.target.matches('[data-formset-delete]')) {
                const form = e.target.closest('[data-formset-form]');
                if (form) {
                    form.remove();
                    formCount--;
                    totalFormsInput.value = formCount;

                    // Execute callback if provided
                    if (options.onDelete) {
                        options.onDelete();
                    }
                }
            }
        });
    }

    /**
     * File upload with progress
     */
    static async uploadFile(fileInput, url, options = {}) {
        const files = fileInput.files;
        if (!files || files.length === 0) {
            Toast.error('Please select a file');
            return;
        }

        const formData = new FormData();
        formData.append('file', files[0]);

        // Add additional fields
        if (options.extraData) {
            Object.keys(options.extraData).forEach(key => {
                formData.append(key, options.extraData[key]);
            });
        }

        // Show loading toast
        const loadingToast = Toast.loading(options.loadingMessage || 'Uploading file...');

        // Upload
        const result = await APIClient.upload(url, formData, options);

        // Dismiss loading toast
        Toast.dismiss(loadingToast);

        // Execute callbacks
        if (result.success && options.onSuccess) {
            options.onSuccess(result);
        } else if (!result.success && options.onError) {
            options.onError(result);
        }

        return result;
    }
}

// Make it globally available
window.FormHandler = FormHandler;
