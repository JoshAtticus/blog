class Modal {
    constructor() {
        this.overlay = null;
        this.title = null;
        this.text = null;
        this.buttons = null;
        this.init();
    }

    init() {
        // Check if modal already exists
        if (document.getElementById('dynamic-modal-overlay')) {
            this.overlay = document.getElementById('dynamic-modal-overlay');
            this.title = this.overlay.querySelector('.modal-title');
            this.text = this.overlay.querySelector('.modal-text');
            this.buttons = this.overlay.querySelector('.modal-buttons');
            return;
        }

        // Create modal structure
        this.overlay = document.createElement('div');
        this.overlay.id = 'dynamic-modal-overlay';
        this.overlay.className = 'modal-overlay';

        const content = document.createElement('div');
        content.className = 'modal-content';

        this.title = document.createElement('div');
        this.title.className = 'modal-title';

        this.text = document.createElement('div');
        this.text.className = 'modal-text';

        this.buttons = document.createElement('div');
        this.buttons.className = 'modal-buttons';

        content.appendChild(this.title);
        content.appendChild(this.text);
        content.appendChild(this.buttons);
        this.overlay.appendChild(content);

        document.body.appendChild(this.overlay);

        // Close on overlay click
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });
    }

    show({ title, body, buttons = [] }) {
        this.title.textContent = title || 'Alert';
        this.text.innerHTML = body || ''; // Allow HTML in body
        this.buttons.innerHTML = '';

        if (buttons.length === 0) {
            // Default OK button
            buttons.push({
                text: 'OK',
                primary: true,
                onClick: () => this.close()
            });
        }

        buttons.forEach(btnConfig => {
            const btn = document.createElement(btnConfig.link ? 'a' : 'button');
            btn.className = `modal-btn ${btnConfig.primary ? 'modal-btn-primary' : 'modal-btn-secondary'}`;
            btn.textContent = btnConfig.text;
            
            if (btnConfig.link) {
                btn.href = btnConfig.link;
                btn.target = '_blank';
                btn.rel = 'noopener noreferrer';
                // Close modal when link is clicked
                btn.addEventListener('click', () => this.close());
            }

            if (btnConfig.onClick) {
                btn.addEventListener('click', (e) => {
                    if (!btnConfig.link) e.preventDefault();
                    btnConfig.onClick(e);
                    if (btnConfig.close !== false) { // Default to close unless specified
                        this.close();
                    }
                });
            } else if (!btnConfig.link) {
                 btn.addEventListener('click', () => this.close());
            }

            this.buttons.appendChild(btn);
        });

        // Force reflow
        void this.overlay.offsetWidth;
        this.overlay.classList.add('open');
    }

    close() {
        this.overlay.classList.remove('open');
    }
}

// Global instance
window.uiModal = new Modal();
