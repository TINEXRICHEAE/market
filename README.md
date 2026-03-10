## Market Shopper – Multi‑Vendor Marketplace (Django)

This repository contains a Django‑based **multi‑vendor shopping app** (“shopping app”) that:

- **Manages buyers and sellers** (custom `Users` model with roles).
- Provides a full **storefront** (products, cart, wishlist, checkout, orders, delivery tracking, disputes).
- Provides a **seller dashboard** (products, sales, KYC, finances).
- Integrates with an external **payment app (Fair Cashier)** via an **iframe + webhooks**.
- Integrates with a **Strapi ZKP app** for **privacy‑preserving proofs**:
  - Buyer balance proofs (payment app is prover, shopping app is verifier).
  - Seller KYC proofs (shopping app is prover, payment app is verifier).

For a detailed, endpoint‑by‑endpoint tour of the system, see `URLS_AND_TEMPLATES.md`.

---

## Tech Stack

- **Backend**: Django 4.2 (`shopper` project, `shopping_app` Django app)
- **Auth**: Custom `Users` model with email as username; roles: buyer, seller, admin, superadmin
- **API**: Django views returning HTML + JSON endpoints (REST‑style), `djangorestframework`
- **Async / background**: Celery (configured via `celery`, `django_celery_results`)
- **DB**: PostgreSQL (via `dj-database-url` and `psycopg2-binary`)
- **Other libs**: `django-guardian`, `django-cors-headers`, `django-phonenumber-field`, `phonenumbers`

Python dependencies live in `shopper/requirements.txt`.

---

## High‑Level Architecture

- **Project**: `shopper/`
  - `shopper/settings.py` – Django settings, external service URLs, CORS/CSRF, logging.
  - `shopper/urls.py` – root URL config; delegates public routes to `shopping_app.urls`.
  - `shopping_app/` – core application:
    - `models.py` – users, products, cart, wishlist, orders, delivery tracking, disputes, seller KYC, balance proofs.
    - `views*.py` – auth, catalog, cart, checkout, orders, seller dashboard, payment proxies, ZKP flows.
    - `urls*.py` – main URLs plus grouped URLs for orders, proxies, balance proofs, seller verification.
    - `templates/` – buyer and seller pages, payment iframe container, ZKP proof UI.
    - `static/` – CSS and JS (navbar behavior, cart/order interactions, etc.).
    - `management/commands/` – data‑seeding commands (e.g. `populate_products`, `populate_buyers`).

Core business entities include:

- `Users` – custom auth model with role field and phone number.
- `Product`, `Category` – catalog, prices, stock and images.
- `Cart`, `CartItem`, `Wishlist` – buyer cart + favorites.
- `Order`, `OrderItem` – multi‑seller orders, per‑item payment methods/status and delivery tracking.
- `OrderItemTracking`, `DeliveryConfirmation`, `OrderDispute` – tracking, confirmations and disputes.
- `SellerVerification` – seller KYC record and ZKP registration metadata.
- `BalanceProofVerification` – verified balance proofs per seller/order from the payment app.

---

## Local Development Setup

### 1. Prerequisites

- Python 3.11+ (a virtualenv is recommended)
- PostgreSQL database
- (Optional but recommended for full flows) Running:
  - **Fair Cashier** payment app
  - **Strapi ZKP** service

### 2. Create and activate a virtual environment

```bash
cd shopper
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in `shopper/` (there is already a reference `.env` loaded in `settings.py`) and set at least:

```bash
DJANGO_SECRET_KEY=change_me
DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/DB_NAME

# External payment app (Fair Cashier)
FAIR_CASHIER_API_KEY=your_fair_cashier_api_key
PAYMENT_APP_URL=http://localhost:8001

# Strapi ZKP app
ZKP_STRAPI_URL=http://localhost:1337
ZKP_STRAPI_API_TOKEN=your_strapi_token

# Internal secret used when payment app pulls seller KYC data
SHOPPING_APP_INTERNAL_SECRET=some-long-random-string
```

You can also adjust `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` in `shopper/settings.py` as needed for your environment (ngrok, LAN IPs, etc.).

### 5. Apply database migrations

```bash
cd shopper
python manage.py migrate
```

Optionally, seed sample data:

```bash
python manage.py populate_products
python manage.py populate_buyers
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

This will create an admin user (role `superadmin` by default) for `/admin/`.

### 7. Run the development server

```bash
python manage.py runserver
```

By default, the app will be available at `http://127.0.0.1:8000/`.

To see logs, check `shopper/logs/django.log` (path configured in `settings.py`).

---

## External Services & Integrations

- **Payment app (Fair Cashier)**:
  - Embedded via an **iframe** (`payment_iframe.html`) at checkout.
  - The shopping app creates payment requests, then hosts the payment UI in an iframe and listens for:
    - **Redirects** (return URL) for overall payment outcome.
    - **Webhooks** (per‑item payment status) to keep `OrderItem.payment_status` in sync.
- **Strapi ZKP app**:
  - Used for:
    - **Balance proofs** – ensuring a buyer’s wallet can cover one/more order items without revealing the raw balance.
    - **Seller verification proofs** – proving to the payment app that a seller completed KYC in the shopping app without leaking full documents.
  - Related models: `SellerVerification`, `BalanceProofVerification`.
  - Related URL groups: `urls_balance_proof.py`, `urls_seller_verification.py`.

For URL‑by‑URL descriptions and how templates hook into these flows, see `URLS_AND_TEMPLATES.md`.

---

Adjust the command to match your actual Celery configuration if it differs.

---

## Useful Entry Points

- **Admin site**: `/admin/`
- **Home / landing page**: `/`
- **Buyer flows**:
  - Product listing: `/products/`
  - Cart: `/cart/`
  - Wishlist: `/wishlist/`
  - Orders: `/orders/`
- **Seller flows**:
  - Dashboard: `/seller/dashboard/`
  - Products: `/seller/products/`
  - Sales: `/seller/sales/`
  - KYC: `/seller/kyc/` and related endpoints.

Again, `URLS_AND_TEMPLATES.md` is the authoritative guide to routes, templates and JSON APIs.

---

## Contributing / Extending

- **New features**: Follow the existing pattern of:
  - Model changes in `shopping_app/models.py` + migrations.
  - Views in `shopping_app/views*.py`.
  - URLs in the appropriate `urls*.py` module.
  - Templates in `shopper/templates/` (typically extending `base.html` and using `navbar_base.html`).
- **Permissions**: Respect the `role` field on `Users` and existing guard logic for buyer vs seller vs admin.
- **ZKP & payment flows**: When changing these, double‑check `URLS_AND_TEMPLATES.md` and the relevant proxy / ZKP view modules so that flows stay consistent across shopping app, payment app, and Strapi.

