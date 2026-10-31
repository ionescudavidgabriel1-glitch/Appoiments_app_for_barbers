# Frontend

Server-rendered Jinja templates served by the Flask app in `backend/`. There is no separate client to run: `flask run` serves the pages.

## Layout

```
frontend/
  templates/
    base.html        layout: header, flash messages, footer
    main/home.html   home page
  static/
    css/app.css      custom styles beyond Tailwind utilities
```

Templates are grouped in folders named after their blueprint (`main/`, `auth/`, `booking/` and so on).

## Pages

| Page | URL | Template |
| --- | --- | --- |
| Home | `/` | `main/home.html` |

## Styling

Tailwind CSS currently loads from the Play CDN in `base.html`, which is for development only. Replace it with a stylesheet built by the Tailwind CLI before deploying (phase 7). HTMX will be added in phase 4 for slot selection.
