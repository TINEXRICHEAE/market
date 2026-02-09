// Global state
let isAuthenticated = false;
let currentUser = {
    email: '',
    role: '',
    phonenumber: ''
};
let csrfToken = '';
let selectedRole = '';

// Initialize on page load
(async function init() {
    await getCSRFToken();
    await checkAuth();
    
    // Only load profile if authenticated
    if (isAuthenticated) {
        await loadUserProfile();
    } else {
        updateUIForUnauthenticated();
    }
    
    // Child-specific initialization
    if (typeof childInit === 'function') {
        await childInit();
    }
})();

// === CSRF Token ===
async function getCSRFToken() {
    try {
        const response = await fetch('/api/csrf/');
        const data = await response.json();
        csrfToken = data.csrfToken;
    } catch (error) {
        console.error('Failed to get CSRF token:', error);
    }
}

// === Authentication ===
async function checkAuth() {
    try {
        const response = await fetch('/check_auth/');
        const data = await response.json();
        isAuthenticated = data.is_authenticated;
    } catch (error) {
        console.error('Auth check failed:', error);
    }
}

// === Load User Profile ===
async function loadUserProfile() {
    try {
        const response = await fetch('/user_profile/');
        const data = await response.json();
        
        if (data.status === 'success') {
            currentUser.email = data.email;
            currentUser.phonenumber = data.phonenumber || '';
            currentUser.role = data.role || 'buyer';
            
            updateUIWithUserData();
            await loadCartCount();
        }
    } catch (error) {
        console.error('Failed to load profile:', error);
    }
}

// === Update UI for Unauthenticated Users ===
function updateUIForUnauthenticated() {
    // Show login link
    const loginLink = document.getElementById('loginLink');
    const mobileLoginLink = document.getElementById('mobileLoginLink');
    if (loginLink) loginLink.style.display = 'inline-block';
    if (mobileLoginLink) mobileLoginLink.style.display = 'block';
    
    // Hide profile button
    const profileBtn = document.getElementById('profileBtn');
    if (profileBtn) profileBtn.style.display = 'none';
    
    // Hide mobile profile section
    const mobileProfileSection = document.getElementById('mobileProfileSection');
    if (mobileProfileSection) mobileProfileSection.style.display = 'none';
    
    // Hide all role-specific links
    hideAllRoleLinks();
}

// === Update UI with User Data ===
function updateUIWithUserData() {
    // Hide login link
    const loginLink = document.getElementById('loginLink');
    const mobileLoginLink = document.getElementById('mobileLoginLink');
    if (loginLink) loginLink.style.display = 'none';
    if (mobileLoginLink) mobileLoginLink.style.display = 'none';
    
    // Show profile button
    const profileBtn = document.getElementById('profileBtn');
    if (profileBtn) profileBtn.style.display = 'flex';
    
    // Show mobile profile section
    const mobileProfileSection = document.getElementById('mobileProfileSection');
    if (mobileProfileSection) mobileProfileSection.style.display = 'block';
    
    // Update navbar email
    const navEmail = document.getElementById('navUserEmail');
    if (navEmail) navEmail.textContent = currentUser.email.split('@')[0];
    
    // Update mobile menu email
    const mobileEmail = document.getElementById('mobileUserEmail');
    if (mobileEmail) mobileEmail.textContent = currentUser.email;
    
    // Update modal
    const modalEmail = document.getElementById('modalUserEmail');
    if (modalEmail) modalEmail.textContent = currentUser.email;
    
    const modalRole = document.getElementById('modalUserRole');
    if (modalRole) modalRole.textContent = currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1);
    
    const phoneInput = document.getElementById('phoneInput');
    if (phoneInput) phoneInput.value = currentUser.phonenumber || '';
    
    // Set active role
    selectedRole = currentUser.role;
    updateRoleUI();
    
    // Update role-specific links
    updateRoleLinks();
}

// === Hide All Role Links ===
function hideAllRoleLinks() {
    // Desktop
    const buyerLinks = document.getElementById('buyerLinks');
    const sellerLinks = document.getElementById('sellerLinks');
    if (buyerLinks) buyerLinks.style.display = 'none';
    if (sellerLinks) sellerLinks.style.display = 'none';
    
    // Mobile
    const mobileBuyerLinks = document.getElementById('mobileBuyerLinks');
    const mobileSellerLinks = document.getElementById('mobileSellerLinks');
    if (mobileBuyerLinks) mobileBuyerLinks.style.display = 'none';
    if (mobileSellerLinks) mobileSellerLinks.style.display = 'none';
}

// === Update Role Links ===
function updateRoleLinks() {
    // Hide all first
    hideAllRoleLinks();
    
    // Show appropriate links based on role
    if (currentUser.role === 'buyer') {
        // Desktop
        const buyerLinks = document.getElementById('buyerLinks');
        if (buyerLinks) buyerLinks.style.display = 'inline';
        
        // Mobile
        const mobileBuyerLinks = document.getElementById('mobileBuyerLinks');
        if (mobileBuyerLinks) mobileBuyerLinks.style.display = 'block';
        
    } else if (currentUser.role === 'seller') {
        // Desktop
        const sellerLinks = document.getElementById('sellerLinks');
        if (sellerLinks) sellerLinks.style.display = 'inline';
        
        // Mobile
        const mobileSellerLinks = document.getElementById('mobileSellerLinks');
        if (mobileSellerLinks) mobileSellerLinks.style.display = 'block';
    }
}

// === Role Management ===
function selectRole(role) {
    selectedRole = role;
    updateRoleUI();
}

function updateRoleUI() {
    document.querySelectorAll('.role-option').forEach(opt => {
        if (opt.dataset.role === selectedRole) {
            opt.classList.add('active');
        } else {
            opt.classList.remove('active');
        }
    });
}

// === Save Profile ===
async function saveProfile() {
    try {
        const phoneNumber = document.getElementById('phoneInput').value;
        let needsReload = false;
        
        // Update phone number
        if (phoneNumber !== currentUser.phonenumber) {
            const phoneResponse = await fetch('/user_profile/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ phonenumber: phoneNumber })
            });
            
            const phoneData = await phoneResponse.json();
            if (phoneData.status !== 'success') {
                showToast(phoneData.message || 'Failed to update phone', 'error');
                return;
            }
        }
        
        // Update role if changed
        if (selectedRole !== currentUser.role) {
            const roleResponse = await fetch('/api/user/update-role/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ role: selectedRole })
            });
            
            if (roleResponse.ok) {
                currentUser.role = selectedRole;
                needsReload = true;
                showToast('Role updated successfully!', 'success');
                setTimeout(() => window.location.reload(), 1500);
                return;
            }
        }
        
        if (!needsReload) {
            showToast('Profile updated successfully!', 'success');
            closeProfileModal();
            await loadUserProfile();
        }
        
    } catch (error) {
        console.error('Error saving profile:', error);
        showToast('Failed to save profile', 'error');
    }
}

// === Delete Account ===
async function handleDeleteAccount() {
    // First confirmation
    const confirmText = 'DELETE';
    const userInput = prompt(
        `⚠️ WARNING: This will permanently delete your account and ALL data!\n\n` +
        `This includes:\n` +
        `- Your profile and personal information\n` +
        `- All orders (for buyers)\n` +
        `- All products and sales (for sellers)\n` +
        `- Your wishlist and cart\n\n` +
        `This action CANNOT be undone!\n\n` +
        `Type "${confirmText}" to confirm deletion:`
    );
    
    if (userInput !== confirmText) {
        if (userInput !== null) {
            showToast('Account deletion cancelled', 'error');
        }
        return;
    }
    
    // Second confirmation
    if (!confirm('Are you absolutely sure? This is your last chance to cancel.')) {
        showToast('Account deletion cancelled', 'error');
        return;
    }
    
    try {
        const response = await fetch('/delete_account/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === 'success') {
            showToast('Account deleted successfully. Goodbye!', 'success');
            setTimeout(() => {
                window.location.href = '/';
            }, 2000);
        } else {
            showToast(data.message || 'Failed to delete account', 'error');
        }
    } catch (error) {
        console.error('Error deleting account:', error);
        showToast('Failed to delete account', 'error');
    }
}

// === Cart Count ===
async function loadCartCount() {
    if (!isAuthenticated || currentUser.role !== 'buyer') return;
    
    try {
        const response = await fetch('/api/cart/');
        const data = await response.json();
        const count = data.total_items || 0;
        
        const badge = document.getElementById('cartBadge');
        const mobileBadge = document.getElementById('mobileCartBadge');
        
        if (badge) badge.textContent = count;
        if (mobileBadge) mobileBadge.textContent = `(${count})`;
    } catch (error) {
        console.error('Failed to load cart count:', error);
    }
}

// === Mobile Menu ===
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    const hamburger = document.getElementById('hamburger');
    
    if (menu && hamburger) {
        menu.classList.toggle('active');
        hamburger.classList.toggle('active');
    }
}

function closeMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    const hamburger = document.getElementById('hamburger');
    
    if (menu && hamburger) {
        menu.classList.remove('active');
        hamburger.classList.remove('active');
    }
}

// === Profile Modal ===
function openProfileModal() {
    if (!isAuthenticated) {
        window.location.href = '/login_user/';
        return;
    }
    
    const modal = document.getElementById('profileModal');
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeProfileModal() {
    const modal = document.getElementById('profileModal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = 'auto';
    }
}

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('profileModal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'profileModal') {
                closeProfileModal();
            }
        });
    }
});

// === Logout ===
async function handleLogout() {
    if (!confirm('Are you sure you want to logout?')) return;
    
    try {
        const response = await fetch('/logout_user/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });
        
        if (response.ok) {
            window.location.href = '/login_user/';
        }
    } catch (error) {
        console.error('Logout failed:', error);
        showToast('Logout failed', 'error');
    }
}

// === Toast Notifications ===
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = message;
        toast.className = `toast ${type} show`;
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
}

// === Utility: Close mobile menu on window resize ===
window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
        closeMobileMenu();
    }
});