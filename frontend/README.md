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
    auth/invite_*.html   invite link: sign up and join, join while logged in, invalid link
    shops/dashboard.html dashboard after login
    shops/shop_form.html create a shop / shop settings
    shops/overview.html  a shop's services, barbers and invites
    shops/service_form.html add or edit a service
    shops/hours.html     a barber's weekly working hours
    booking/book.html    public booking page (service, barber, day and time, details)
    booking/confirmation.html the guest's booking page, with change and cancel
    booking/_steps.html  barber and day/time steps, shared by booking and reschedule
    booking/reschedule.html move a booking (guests and the shop)
    calendar/day.html    the shop's day: one ledger per barber
    calendar/appointment.html one booking with its actions
    calendar/time_off.html a barber's time off
    calendar/_status.html status_pill macro (Booked, Completed, No-show...)
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
| Create a shop | `/shops/new` | `shops/shop_form.html` |
| Shop settings | `/shops/<slug>/settings` | `shops/shop_form.html` |
| Shop overview | `/shops/<slug>/` | `shops/overview.html` |
| Add or edit a service | `/shops/<slug>/services/...` | `shops/service_form.html` |
| Working hours | `/shops/<slug>/barbers/<id>/hours` | `shops/hours.html` |
| Book (public) | `/s/<slug>/` | `booking/book.html` |
| Guest's booking | `/s/<slug>/booking/<token>` | `booking/confirmation.html` |
| Guest moves a booking | `/s/<slug>/booking/<token>/reschedule` | `booking/reschedule.html` |
| Calendar | `/shops/<slug>/calendar` | `calendar/day.html` |
| One booking | `/shops/<slug>/appointments/<id>` | `calendar/appointment.html` |
| Shop moves a booking | `/shops/<slug>/appointments/<id>/reschedule` | `booking/reschedule.html` |
| Time off | `/shops/<slug>/barbers/<id>/time-off` | `calendar/time_off.html` |
| Accept an invite | `/auth/invite/<token>` | `auth/invite_signup.html`, `auth/invite_join.html`, `auth/invite_invalid.html` |

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

`field` shows the label, the input, a hint (the field's `description`) and any validation errors, and adds a Show/Hide button to password fields. `submit` takes the button label and the label shown while the form is sending.

For actions that only need a button, like hiding a service, use `post_button(url, label, style=...)`. Import it `with context`, because it uses the `action_form` CSRF token that every page gets.

Destructive actions (cancelling a booking) use a two-step `<details>` box: the first button opens it, the second confirms. It works without JavaScript.

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
- `.ledger`, `.ledger-row`, `.ledger-time` and `.slot` (`.slot-free`, `.slot-booked`) for the appointment book, used for slot picking and (phase 5) the daily calendar.
- `.choice` wraps a hidden radio with a `.choice-card` (or a `.slot` chip) so radios look like cards; `.day-strip` is the sideways-scrolling day picker.
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
- `data-copy="input-id"` on a button copies that input's value (the invite link).
- On the working hours page, "Copy Monday to Tuesday–Friday" fills in the weekdays.
- On the booking page, the Book button names the picked time, and after HTMX swaps in the next step it scrolls into view (`data-focus`).

## Page checks

Playwright is in `requirements-dev.txt`. After `python -m playwright install chromium`, write scripts that open pages in a headless browser and take screenshots at desktop (1280px) and phone (390px) widths.

## Styling

Tailwind CSS currently loads from the Play CDN in `base.html`, with the colors and fonts above registered in `tailwind.config`. The CDN is for development only. Replace it with a stylesheet built by the Tailwind CLI before deploying (phase 7). HTMX (2.0.4, from unpkg) is loaded only on the booking page through the `head_scripts` block. The booking form has `hx-get` on itself: changing a radio marked `data-refresh` reloads the page with the choices in the URL and swaps only `#steps`. Without JavaScript, a "Show times" button does the same with a normal page load.

Public pages for guests override the `nav` block to hide the owner and barber login links.
