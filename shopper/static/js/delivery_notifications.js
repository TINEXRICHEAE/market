// File: static/js/delivery_notifications.js

(function () {
    // Only run for authenticated buyers
    const CHECK_INTERVAL = 30000; // 30 seconds
    let notificationShown = false;

    function initDeliveryNotifications() {
        // Wait for auth check to complete
        const waitForAuth = setInterval(() => {
            if (typeof isAuthenticated !== 'undefined' && typeof currentUser !== 'undefined') {
                clearInterval(waitForAuth);
                if (isAuthenticated && currentUser.role === 'buyer') {
                    checkForDeliveries();
                    setInterval(checkForDeliveries, CHECK_INTERVAL);
                }
            }
        }, 500);
    }

    async function checkForDeliveries() {
        try {
            const resp = await fetch('/api/pending-deliveries/');
            if (!resp.ok) return;

            const data = await resp.json();

            if (data.has_pending && data.notifications.length > 0 && !notificationShown) {
                showDeliveryPopup(data.notifications);
            }
        } catch (err) {
            // Silently fail — not critical
        }
    }

    function showDeliveryPopup(notifications) {
        notificationShown = true;

        // Create overlay
        const overlay = document.createElement('div');
        overlay.id = 'deliveryNotificationOverlay';
        overlay.style.cssText = `
            position: fixed; inset: 0; z-index: 10000;
            background: rgba(0,0,0,0.5);
            display: flex; align-items: center; justify-content: center;
            animation: fadeIn 0.3s ease;
        `;

        // Build items list
        const itemsList = notifications.map(n => `
            <div style="display:flex; justify-content:space-between; align-items:center;
                        background:#fffbeb; border:1px solid #fbbf24; border-radius:8px;
                        padding:12px 16px; margin-bottom:8px;">
                <div>
                    <p style="font-weight:700; font-size:14px; color:#92400e;">
                        📦 Order ${n.order_number}
                    </p>
                    <p style="font-size:12px; color:#78716c;">
                        ${n.items_count} item(s) marked as delivered
                    </p>
                </div>
                <a href="/order/${n.order_id}/confirm-delivery/"
                   style="background:#f59e0b; color:white; padding:8px 16px;
                          border-radius:6px; font-size:12px; font-weight:700;
                          text-decoration:none; white-space:nowrap;">
                    Review →
                </a>
            </div>
        `).join('');

        overlay.innerHTML = `
            <div style="background:white; border-radius:16px; max-width:460px; width:90%;
                        box-shadow:0 25px 50px rgba(0,0,0,0.25); overflow:hidden;
                        animation: slideUp 0.3s ease;">
                <div style="background:#f59e0b; padding:20px 24px; text-align:center;">
                    <span style="font-size:40px; display:block; margin-bottom:8px;">📦🔔</span>
                    <h2 style="color:white; font-size:18px; font-weight:800; margin:0;">
                        Delivery Update!
                    </h2>
                    <p style="color:rgba(255,255,255,0.9); font-size:13px; margin-top:4px;">
                        Your seller has marked items as delivered.
                    </p>
                </div>
                <div style="padding:20px 24px;">
                    ${itemsList}
                    <p style="font-size:11px; color:#9ca3af; text-align:center; margin-top:12px;">
                        Please review each order and confirm receipt or report issues.
                    </p>
                </div>
                <div style="padding:12px 24px 20px; text-align:center; border-top:1px solid #f3f4f6;">
                    <button onclick="dismissDeliveryPopup()"
                            style="background:#f3f4f6; color:#6b7280; border:none; padding:10px 24px;
                                   border-radius:8px; font-size:13px; font-weight:600; cursor:pointer;">
                        Dismiss — I'll review later
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
    }

    // Global dismiss function
    window.dismissDeliveryPopup = function () {
        const overlay = document.getElementById('deliveryNotificationOverlay');
        if (overlay) {
            overlay.style.animation = 'fadeOut 0.2s ease';
            setTimeout(() => overlay.remove(), 200);
        }
    };

    // Inject CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }
        @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
    `;
    document.head.appendChild(style);

    // Start
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDeliveryNotifications);
    } else {
        initDeliveryNotifications();
    }
})();
