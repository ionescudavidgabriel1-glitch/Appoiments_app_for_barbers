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
    css/app.css      design tokens and components (buttons, inputs, ledger, animations)
    js/app.js        small interactions (see "Interactions")
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
  {{ submit("Save changes", "Saving…") }}
</form>
```

`field` shows the label, the input and any validation errors, and adds a Show/Hide button to password fields. `submit` takes the button label and the label shown while the form is sending.

Flash messages use the categories `success` (mint), `error` (oxblood) and `info` (brass). Success and info messages fade out after 6 seconds; errors stay until closed.

Write error messages as plain directions, e.g. "Use at least 8 characters.", not "Field must be between 8 and 128 characters long."

## Design

The look is "the appointment book": a warm, welcoming barbershop, with the ruled column of times from a shop's paper appointment book as the one signature element.

| Token | Hex | Tailwind class | Use |
| --- | --- | --- | --- |
| Towel | `#FAF6F1` | `towel` | page background |
| Walnut | `#3A2A22` | `walnut` | text |
| Oxblood | `#7A1F2B` | `oxblood` | primary buttons, booked slots, errors |
| Chair mint | `#BFE3D5` | `mint` (`mint-deep` for text on it) | free slots, success |
| Brass | `#B7843A` | `brass` | focus outline, highlights |
| Taupe | `#6F625A` | `taupe` | secondary text |
| Line | `#E8DFD5` | `line` | borders, ledger rules |
| Steam | `#F1EAE2` | `steam` | hover backgrounds |

Fonts: Big Shoulders Display for headings (`font-display`), Figtree for everything else.

Components in `app.css`:
- `.btn` with `.btn-primary` (oxblood, barber-pole stripes on hover), `.btn-quiet` (white, outlined), and `.btn-link` for header links. Buttons lift on hover and squish on press.
- `.input` for text fields, with a brass focus ring.
- `.ledger`, `.ledger-row`, `.ledger-time` and `.slot` (`.slot-free`, `.slot-booked`) for the appointment book. Phases 4 and 5 reuse these for slot picking and the daily calendar.
- `.page-enter` on a wrapper makes its children rise in once on load.
- `.pole` is the logo's turning barber pole.

All animation stops for visitors who set "reduce motion" on their device.

## Interactions

`static/js/app.js` adds feedback on top of pages that work without it:
- Submit buttons show a spinner and their loading label.
- Flash messages can be closed and fade out on their own.
- Password fields get Show/Hide.
- `data-greet="Name"` turns a heading into "Good morning, Name" by the visitor's local time.
- The home page demo lets visitors book and free sample slots.

## Page checks

Playwright is in `requirements-dev.txt`. After `python -m playwright install chromium`, write scripts that open pages in a headless browser and take screenshots at desktop (1280px) and phone (390px) widths.

## Styling

Tailwind CSS currently loads from the Play CDN in `base.html`, with the colors and fonts above registered in `tailwind.config`. The CDN is for development only. Replace it with a stylesheet built by the Tailwind CLI before deploying (phase 7). HTMX will be added in phase 4 for slot selection.
