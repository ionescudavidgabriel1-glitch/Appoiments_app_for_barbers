# Frontend

Server-rendered Jinja templates served by the Flask app in `backend/`. There is no separate client to run: `flask run` serves the pages.

## Layout

```
frontend/
  templates/
    base.html            layout: header with login/logout links, flash messages, footer
    _form.html           macros for form fields and submit buttons
    main/home.html       home page
    auth/signup.html     owner sign up
    auth/login.html      log in
    shops/dashboard.html dashboard after login
  static/
    css/app.css      custom styles beyond Tailwind utilities
```

Templates are grouped in folders named after their blueprint (`main/`, `auth/`, `booking/` and so on).

## Pages

| Page | URL | Template |
| --- | --- | --- |
| Home | `/` | `main/home.html` |
| Sign up | `/auth/signup` | `auth/signup.html` |
| Log in | `/auth/login` | `auth/login.html` |
| Dashboard | `/shops/` | `shops/dashboard.html` |

## Forms

Build form fields with the macros in `_form.html`:

```jinja
{% from "_form.html" import field, submit %}
<form method="post" novalidate>
  {{ form.hidden_tag() }}   {# CSRF token #}
  {{ field(form.email, autocomplete="email") }}
  {{ submit("Save") }}
</form>
```

`field` shows the label, the input and any validation errors. Flash messages use the categories `success` (green), `error` (red) and `info` (blue).

## Styling

Tailwind CSS currently loads from the Play CDN in `base.html`, which is for development only. Replace it with a stylesheet built by the Tailwind CLI before deploying (phase 7). HTMX will be added in phase 4 for slot selection.
