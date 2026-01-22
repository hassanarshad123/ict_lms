// Customize login page - replace signup link with Zensbot branding
frappe.ready(function() {
    // Check if we're on the login page
    if (window.location.pathname === '/login' || window.location.hash === '#login') {
        // Find the signup link container
        var signupLink = document.querySelector('.sign-up-message, .signup-message, [data-action="signup"]');
        if (!signupLink) {
            // Try alternative selector for the "Don't have an account? Sign up" text
            signupLink = document.querySelector('.page-card-actions p, .login-content p:last-child');
        }

        if (signupLink && signupLink.textContent.includes('Sign up')) {
            signupLink.innerHTML = '<a href="https://zensbot.com" target="_blank" style="color: var(--text-muted);">Built by Zensbot.com</a>';
        }
    }
});
