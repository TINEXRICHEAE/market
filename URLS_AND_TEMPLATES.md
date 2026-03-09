## URL and Template Guide

This document explains what each URL and the main templates in the **shopping app** do, to help you navigate and extend the project.

---

## Project Overview (What this system is)

This repo is a Django **multi-vendor shopping app** (buyers + sellers) that integrates with:

- **A payment app (Fair Cashier)** that is rendered inside this shopping app via an **iframe** to handle wallet actions and online payments.
- **A Strapi ZKP app** that both the shopping app and the payment app talk to, to support **privacy-preserving proofs** between the two apps.

### Main components and roles

- **Shopping app (this repo)**  
  - Owns: users, products, cart, orders, KYC collection for sellers (documents + status).  
  - Renders: storefront + seller dashboard + buyer order flows.  
  - Integrates with payment app via:
    - **iframe container** (`payment_iframe.html` via `proxy_views.payment_iframe_proxy`)
    - **redirect return handler** (`proxy_views.payment_return`)
    - **webhook receiver** for per-item payment status (`proxy_views.payment_status_webhook`)

- **Payment app (Fair Cashier)**  
  - Owns: buyer/seller wallets, balances, deposits, PIN flows, settlement to sellers.  
  - Embedded in an iframe during checkout so the shopping app never needs to directly render wallet/payment UI.

- **Strapi ZKP app**  
  - Owns: proof/verification endpoints and coordination for ZKP-style workflows between shopping and payment apps.

### Payment UX summary (iframe)

At checkout, the shopping app creates an order and (if online payment is needed) creates a **payment request** in the payment app. The buyer is then sent to a shopping-app page that embeds the payment app screen inside an **iframe**:

- The shopping app page is the “container” (it knows the order/request context).
- The payment app page inside the iframe handles wallet deposit/payment and then redirects back to the shopping app’s return URL with a status (`success`, `deposited`, `cancelled`, `failed`).
- The payment app can also push updates to the shopping app via webhook so per-item payment statuses stay synchronized.

### Strapi ZKP integrations (2 privacy-preserving cases)

Both the shopping app and payment app interact with the Strapi ZKP app for two cases.

#### 1) Balance checks (Payment app = prover, Shopping app = verifier)

**Goal**: A seller (viewing an order in the shopping app) needs to know whether the buyer has **enough wallet funds** in the payment app to cover the required amount **without revealing the actual balance** to the shopping app.

- **Prover**: Payment app (knows the real wallet balance).
- **Verifier**: Shopping app (needs a yes/no assurance for “balance ≥ required amount”).
- **Privacy property**: The shopping app learns only proof outcome / metadata, not the buyer’s balance.

In code, order creation triggers balance-proof requests (see `views.process_payment_selection` calling `views_balance_proof.request_balance_proofs_for_order`), and related balance-proof URLs are included via `balance_proof_urlpatterns`.

#### 2) Seller verifications (Shopping app = prover, Payment app = verifier)

**Goal**: The payment app must verify that sellers have submitted and completed KYC in the shopping app, **without receiving the sensitive KYC documents/PII** that the shopping app collected.

- **Prover**: Shopping app (holds KYC data + approval decision).
- **Verifier**: Payment app (needs assurance seller KYC is done/approved).
- **Privacy property**: Payment app learns only proof outcome / safe metadata, not raw KYC documents.

The buyer-facing order detail UI (`order_detail.html`) includes per-seller “ZKP verified” badges and a proof modal powered by `/api/seller-verification-status/<seller_id>/` (routes included via `seller_verification_urlpatterns`).

---

## Project URL Entry Point

- **`/admin/`**  
  - **Module**: `shopper/shopper/urls.py`  
  - **Handler**: Django admin site  
  - **Template**: Django admin built‑ins  
  - **Purpose**: Standard Django admin interface.

- **`''` (root) → `shopping_app.urls`**  
  - **Module**: `shopper/shopper/urls.py`  
  - **Purpose**: Delegates all public and API routes to the `shopping_app` application.

---

## Authentication & User Management URLs

- **`/register_user/`**  
  - **View**: `views.register_user`  
  - **Template**: `signup.html` (for GET)  
  - **Purpose**: Register as buyer or seller. POST expects `email`, `password1`, `password2`, and optional `register_as_seller` and returns JSON; GET serves the sign‑up page UI.

- **`/login_user/`**  
  - **View**: `views.login_user`  
  - **Template**: `login.html` (for GET)  
  - **Purpose**: Email/password login. POST returns JSON indicating success/failure; GET renders the login UI.

- **`/check_auth/`**  
  - **View**: `views.check_auth`  
  - **Template**: none (JSON)  
  - **Purpose**: Lightweight endpoint returning `{"is_authenticated": true/false}` for front‑end logic.

- **`/logout_user/`**  
  - **View**: `views.logout_user`  
  - **Template**: none (JSON)  
  - **Purpose**: POST logs out current user and returns JSON; used by navbar/profile UI.

- **`/user_profile/`**  
  - **View**: `views.user_profile`  
  - **Template**: none (JSON)  
  - **Purpose**:  
    - GET: returns profile fields (email, phone, role).  
    - POST: update phone number; used by profile modal in `navbar_base.html`.

- **`/delete_account/`**  
  - **View**: `views.delete_account`  
  - **Template**: none (JSON)  
  - **Purpose**: Permanently deletes the authenticated user account and logs them out.

- **`/api/csrf/`**  
  - **View**: `views.get_csrf_token`  
  - **Template**: none (JSON)  
  - **Purpose**: Provides a CSRF token to JavaScript clients for subsequent POST/PUT/DELETE calls.

- **`/api/user/details/`**  
  - **View**: `views.get_user_details`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns full user details (id, email, role, phone, timestamps) for navbar/profile initialization.

- **`/api/user/update-role/`**  
  - **View**: `views.update_user_role`  
  - **Template**: none (JSON)  
  - **Purpose**: Allows switching between `buyer` and `seller` roles from the profile modal (cannot change admin roles).

- **`/api/user/update-password/`**  
  - **View**: `views.update_user_password`  
  - **Template**: none (JSON)  
  - **Purpose**: Change current user password with validation (current password check, minimum length).

---

## Home and Layout Templates

- **`/`**  
  - **View**: `views.home`  
  - **Template**: `home.html`  
  - **Purpose**: Landing page for the marketplace with marketing sections for buyers and sellers and calls‑to‑action to register and browse products.

- **`base.html`**  
  - **Usage**: Base layout wrapper with `{% block title %}`, `{% block content %}`, `{% block extra_js %}`.  
  - **Includes**: `navbar_base.html` and static navbar JS/CSS.  
  - **Purpose**: Shared layout skeleton; individual pages can extend it, though some key pages use standalone HTML.

- **`navbar_base.html`**  
  - **Usage**: Included at the top of most templates.  
  - **Purpose**: Responsive top navigation bar, showing:
    - Public links (`/`, `/products/`),
    - Buyer links (`/cart/`, `/wishlist/`, `/orders/`),
    - Seller links (`/seller/dashboard/`, `/seller/products/`, `/seller/orders/`, `/seller/cashout/`),
    - Profile modal, delete‑account controls, and KYC quick‑access links.
  - Works together with `static/js/navbar.js` to:
    - Detect authentication and user role,
    - Update badges (cart count, KYC badge),
    - Wire profile actions (`/user_profile/`, `/logout_user/`, etc.).

---

## Product Catalog URLs & Templates

- **`/products/`**  
  - **View**: `views.product_list`  
  - **Template**: `product_list.html`  
  - **Purpose**: Product listing page with search bar and grid.  
  - **Front‑end behavior**:
    - On load, JS calls `/api/products/` to fetch all active products.
    - Search input debounces and reloads via `/api/products/?search=...`.
    - Clicking a card navigates to `/products/<id>/`.
    - “Add to Cart” buttons call `/api/cart/add/`.

- **`/api/products/`**  
  - **View**: `views.get_products`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns filtered product list with fields like id, name, description, price, stock status, category, seller email; consumed by `product_list.html`.

- **`/products/<int:product_id>/`**  
  - **View**: `views.product_detail`  
  - **Template**: `product_detail.html`  
  - **Purpose**: Product detail page with large image, description, quantity controls, and wishlist toggle.  
  - **Front‑end behavior**:
    - JS fetches `/api/products/<product_id>/` to load product details.
    - `Add to cart` calls `/api/cart/add/`.
    - Wishlist button calls `/api/wishlist/toggle/`.

- **`/api/products/<int:product_id>/`**  
  - **View**: `views.get_product_detail`  
  - **Template**: none (JSON)  
  - **Purpose**: Detailed JSON for a single product including `is_in_wishlist` for the current user.

- **`/api/categories/`**  
  - **View**: `views.get_categories`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns list of categories to populate seller product forms.

---

## Cart URLs & Template

- **`/cart/`**  
  - **View**: `views.view_cart`  
  - **Template**: `cart.html`  
  - **Purpose**: Full shopping cart page showing items, quantities, subtotals, and total.  
  - **Front‑end behavior**:
    - On load, JS calls `/api/cart/` to populate the cart.
    - “+/-” buttons update quantities via `/api/cart/update/<item_id>/`.
    - “Remove” buttons call `/api/cart/remove/<item_id>/`.
    - “Proceed to Checkout” redirects to `/checkout/` if cart not empty.

- **`/api/cart/`**  
  - **View**: `views.get_cart`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns current user’s cart contents, totals, and item count.

- **`/api/cart/add/`**  
  - **View**: `views.add_to_cart`  
  - **Template**: none (JSON)  
  - **Purpose**: Adds a product to cart (or increments quantity) while validating stock.

- **`/api/cart/update/<int:item_id>/`**  
  - **View**: `views.update_cart_item`  
  - **Template**: none (JSON)  
  - **Purpose**: Updates quantity or removes item when quantity <= 0.

- **`/api/cart/remove/<int:item_id>/`**  
  - **View**: `views.remove_from_cart`  
  - **Template**: none (JSON)  
  - **Purpose**: Deletes a specific cart item.

---

## Wishlist URLs & Template

- **`/wishlist/`**  
  - **View**: `views.view_wishlist`  
  - **Template**: `wishlist.html`  
  - **Purpose**: UI page listing saved favorite products; populated via JS from the API.

- **`/api/wishlist/`**  
  - **View**: `views.get_wishlist`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns all wishlist items for the current user.

- **`/api/wishlist/toggle/`**  
  - **View**: `views.toggle_wishlist`  
  - **Template**: none (JSON)  
  - **Purpose**: Adds or removes a product from wishlist; used from `product_detail.html`.

- **`/api/wishlist/remove/<int:wishlist_id>/`**  
  - **View**: `views.remove_from_wishlist`  
  - **Template**: none (JSON)  
  - **Purpose**: Explicitly remove a given wishlist entry.

---

## Checkout, Orders & Order Detail Templates

- **`/checkout/`**  
  - **View**: `views.checkout`  
  - **Template**: none (redirect)  
  - **Purpose**: Redirects to `payment_selection_page` after basic checks; this is the entry point from the cart into payment selection.

- **`/payment/select/`**  
  - **View**: `views.payment_selection_page`  
  - **Template**: `payment_selection.html`  
  - **Purpose**: Lets the buyer choose payment method (cash vs online) per seller/cart item.  
  - **Behavior**:
    - Groups cart items by seller.
    - Calls the payment app (`/api/check-sellers/`) to see which sellers can accept online payment.
    - Stores seller payment capabilities in session for use when creating the order.

- **`/api/process-payment-selection/`**  
  - **View**: `views.process_payment_selection`  
  - **Template**: none (JSON)  
  - **Purpose**: Processes form selections from `payment_selection.html`:
    - Creates `Order` and `OrderItem`s,
    - Updates product stock,
    - Optionally creates a payment request in the external payment app and stores `pending_payment` in session,
    - Triggers balance proof generation via ZKP.

- **`/orders/`**  
  - **View**: `views.view_orders`  
  - **Template**: `orders.html`  
  - **Purpose**: Buyer’s orders list page, populated by `/api/orders/`.

- **`/api/orders/`**  
  - **View**: `views.get_orders`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns all orders for the current buyer, including summary item data.

- **`/orders/<int:order_id>/`**  
  - **View**: `views.view_order_detail`  
  - **Template**: `order_detail.html`  
  - **Purpose**: Detailed buyer order page, showing each item’s payment method and status and per‑seller breakdown, plus deposit completion/cancel flows and ZKP seller‑verification badges.

- **`/api/orders/<int:order_id>/`**  
  - **View**: `views.get_order_detail`  
  - **Template**: none (JSON)  
  - **Purpose**: Provides a rich JSON representation of a single order, including:
    - Per‐item payment details,
    - Seller payment summaries,
    - Flags for unpaid online items and counts for pending/deposited.
  - Consumed by `order_detail.html`.

- **`/api/orders/<int:order_id>/retry-payment/`**  
  - **View**: `views.retry_online_payment`  
  - **Template**: none (JSON)  
  - **Purpose**: Re‑creates a payment request for pending/deposited/failed online items in a given order.

- **`/api/orders/<int:order_id>/pay-selected-items/`**  
  - **View**: `views.retry_selected_items_payment`  
  - **Template**: none (JSON)  
  - **Purpose**: Creates a payment request only for selected items in an order (partial payment).

- **`/api/orders/<int:order_id>/items/<int:order_item_id>/complete-deposit/`**  
  - **View**: `views.complete_deposit_item_proxy`  
  - **Template**: none (JSON)  
  - **Purpose**: With buyer PIN, instructs payment app to convert a deposited wallet reserve into a completed payment for a specific order item.

- **`/api/orders/<int:order_id>/items/<int:order_item_id>/cancel-deposit/`**  
  - **View**: `views.cancel_deposit_item_proxy`  
  - **Template**: none (JSON)  
  - **Purpose**: With buyer PIN, cancels a deposited reserve for the given item and returns funds to available balance.

### Additional Order‑related Templates

- **`buyer_order_tracking.html`**  
  - Likely used with a `/order/<id>/tracking/` style URL (visible in `order_detail.html` links) to show a timeline of delivery progress.

- **`delivery_confirmation.html`**  
  - Confirms receipt/delivery of an order; typically used from tracking or order detail flows.

---

## Seller Dashboard & Product Management URLs / Templates

- **`/seller/dashboard/`**  
  - **View**: `views.seller_dashboard`  
  - **Template**: `seller_dashboard.html`  
  - **Purpose**: Main seller overview with statistics like total products, orders, revenue, pending payments, and low stock items (data from `/api/seller/dashboard-stats/`).

- **`/seller/sales/`**  
  - **View**: `views.seller_sales`  
  - **Template**: `seller_sales.html`  
  - **Purpose**: UI page to inspect individual sales (order items) and payment statuses; backed by `/api/seller/sales/` and `/api/seller/recent-sales/`.

- **`/seller/products/`**  
  - **View**: `views.seller_products`  
  - **Template**: `seller_products.html`  
  - **Purpose**: Seller product management dashboard listing all their products via `/api/seller/products/`.

- **`/seller/products/add/`**  
  - **View**: `views.seller_add_product`  
  - **Template**: `seller_add_product.html`  
  - **Purpose**: UI form to add new products; posts to `/api/seller/products/create/`.

- **`/seller/products/edit/<int:product_id>/`**  
  - **View**: `views.seller_edit_product`  
  - **Template**: `seller_edit_product.html`  
  - **Purpose**: UI for editing an existing product; loads details from `/api/seller/products/<product_id>/`.

- **`/api/seller/products/`**  
  - **View**: `views.get_seller_products`  
  - **Template**: none (JSON)  
  - **Purpose**: Lists all products for the authenticated seller.

- **`/api/seller/products/create/`**  
  - **View**: `views.create_product`  
  - **Template**: none (JSON)  
  - **Purpose**: Creates a new product with validation and optional image upload.

- **`/api/seller/products/<int:product_id>/`**  
  - **View**: `views.get_seller_product_detail`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns full editable details for a seller’s own product.

- **`/api/seller/products/<int:product_id>/update/`**  
  - **View**: `views.update_product`  
  - **Template**: none (JSON)  
  - **Purpose**: Updates fields and image/URL for an existing product.

- **`/api/seller/products/<int:product_id>/delete/`**  
  - **View**: `views.delete_product`  
  - **Template**: none (JSON)  
  - **Purpose**: Deletes a seller’s product and associated image file.

- **`/api/seller/dashboard-stats/`**  
  - **View**: `views.get_seller_dashboard_stats`  
  - **Template**: none (JSON)  
  - **Purpose**: Provides aggregate numbers for the seller dashboard.

- **`/api/seller/sales/`**  
  - **View**: `views.get_seller_sales`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns all order items for the seller with payment method/status info.

- **`/api/seller/recent-sales/`**  
  - **View**: `views.get_seller_recent_sales`  
  - **Template**: none (JSON)  
  - **Purpose**: Returns a small set of recent sales for dashboard widgets.

### Seller Order & Finance Templates

- **`seller_orders.html`**  
  - List of orders (grouped by buyer) from the seller’s perspective; typically paired with seller‑prefixed order APIs.

- **`seller_order_detail.html`**  
  - Detailed view of a specific order for a seller, including payment statuses and item information.

- **`seller_finances.html`**  
  - Higher‑level finance view for sellers (e.g., earnings over time, balances and payouts).

---

## Seller KYC & Verification Templates

- **`seller_verification_form.html`**  
  - Page where sellers upload and submit KYC information (documents and fields).  
  - Likely wired to seller KYC APIs declared in `urls_seller_verification.py`, using partial templates:
    - `partials/kyc_field.html`: Render individual text/KYC input fields.
    - `partials/file_upload_field.html`: Styled file upload component.

- **`seller_verification_status.html`**  
  - Read‑only status page showing whether KYC is approved/pending/rejected and any next steps.

- **`seller_kyc_access_denied.html`**  
  - Shown when seller attempts to access KYC‑gated areas before verification or without correct role.

---

## Buyer‑Side ZKP & Seller Proof UI

- **`order_detail.html`**  
  - **View**: `views.view_order_detail` (HTML) + `views.get_order_detail` (JSON)  
  - **Purpose**:
    - Shows detailed order info, item payment statuses, and per‑seller payment breakdown.
    - Integrates:
      - **ZKP seller verification badges** (`.zkp-mini` elements) for each seller of the order.
      - A **Proof Modal** driven by `/api/seller-verification-status/<seller_id>/` that shows:
        - KYC/verification status,
        - High‑level, privacy‑preserving proof data.
      - A **PIN modal** used when completing or cancelling deposited payments item‑by‑item.

---

## Payment App Proxy & Iframe URLs / Templates

These URLs are defined via `proxy_urlpatterns`, `seller_proxy_urlpatterns`, and `order_urlpatterns` imported in `shopping_app/urls.py`. Key endpoints include:

- **`/payment/iframe/<uuid:request_id>/`** (shape defined in `proxy_urlpatterns`)  
  - **View**: `proxy_views.payment_iframe_proxy`  
  - **Template**: `payment_iframe.html`  
  - **Purpose**:
    - Hosts the external payment app in an iframe for a given `request_id`.
    - Ensures the `request_id` matches the `pending_payment` session object (prevents hijacking).
    - Provides the iframe URL and context (amount, order number) to the template.

- **`/payment/return/`**  
  - **View**: `proxy_views.payment_return`  
  - **Template**: none (redirects)  
  - **Purpose**:
    - Landing endpoint for the payment app’s redirect back.
    - Reads `request_id` and `status` from query parameters.
    - Updates `Order` and `OrderItem` payment status and redirects to either order detail, orders, or cart.

- **`/payment/webhook/`** (exact path inside `proxy_urlpatterns`)  
  - **View**: `proxy_views.payment_status_webhook`  
  - **Template**: none (JSON)  
  - **Purpose**:
    - Receives per‑item payment status updates from the payment app.
    - Updates `OrderItem.payment_status` and `Order.online_payment_status` atomically.

- **`/proxy/check-buyer-status/`** (exact path in `proxy_urls`)  
  - **View**: `proxy_views.check_buyer_fair_cashier_status`  
  - **Template**: none (JSON)  
  - **Purpose**:
    - Let front‑end flows know whether the buyer exists and has a wallet/PIN in the payment app to route to setup vs login.

---

## Balance Proof & Seller Verification (ZKP) URLs

Additional URL groups are pulled into `shopping_app/urls.py`:

- **`seller_verification_urlpatterns`** (from `urls_seller_verification.py`)  
  - Includes endpoints such as:
    - `/seller/kyc/` → KYC form and status pages.  
    - `/api/seller/kyc-status/` → JSON powering the KYC badge in `navbar_base.html`.  
    - `/api/seller-verification-status/<int:seller_id>/` → JSON for ZKP seller proof, used by `order_detail.html`.

- **`balance_proof_urlpatterns`** (from `urls_balance_proof.py`)  
  - Includes endpoints around balance proof requests and status queries, such as:
    - `/api/balance-proofs/order/<int:order_id>/` → aggregated balance proofs per seller for an order.  
    - Other internal APIs consumed by background proof generation in `process_payment_selection`.

These URL modules work together with the Strapi ZKP service so that:

- The **shopping app** can verify buyer wallet sufficiency without seeing the exact balance.
- The **payment app** can verify seller KYC status based on proof data exposed via these APIs.

---

## Miscellaneous Templates

- **`signup.html`**  
  - UI for registration; posts to `/register_user/`.

- **`login.html`**  
  - UI for logging in; posts to `/login_user/`.

- **`payment_selection.html`**  
  - Used by `/payment/select/` to let buyers choose per‑seller payment options.

- **`payment_iframe.html`**  
  - Container for the payment app iframe, driven by `payment_iframe_proxy`.

- **`orders.html`**  
  - Buyer’s order history list; consumes `/api/orders/`.

- **`seller_sales.html`, `seller_finances.html`, `seller_orders.html`, `seller_order_detail.html`**  
  - Various seller‑side UIs for order, payout, and sales analytics views; all backed by seller‑side APIs in `views.py` and related URL modules.

This guide should give you a quick mental map of **which URL hits which view and which template**, and how the front‑end pages relate to the JSON APIs and external payment/ZKP integrations.

