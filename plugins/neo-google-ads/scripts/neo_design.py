#!/usr/bin/env python3
"""The NEO design system, as far as a page without a build step needs it.

Two very different pages share it: the public one, which is a business
card, and the management console behind the sign-in, which is a tool.
Both take their colours, sizes, spacing and building blocks from the same
place, so that changing a token changes both.

What is here comes from the design system (tokens/, base/) and is meant
to stay close to it. What a single page needs alone stays with that page.

THE ICONS ARE DRAWN HERE, not loaded from Google's font service. A page
that is being reviewed over data protection should not report the visit
to a third party, and a console on a server should not stop looking like
itself when that server has no way out to the internet.

No build step, no third-party library, no JavaScript.
"""
from __future__ import annotations

import html


def esc(wert) -> str:
    return html.escape(str(wert), quote=True)


# --------------------------------------------------------------------------
# Symbole. Ein 24er-Raster, Strich 1.8, rund abgeschlossen — passend zu den
# Material Symbols des Entwurfs, aber im eigenen Quelltext.
# --------------------------------------------------------------------------
_PFADE = {
    "login": "M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5M10 8l4 4-4 4M14 12H3",
    "science": "M9 3h6M10 3v6.2L5.2 18A2 2 0 0 0 7 21h10a2 2 0 0 0 1.8-2.9L14 9.2V3"
               "M7.8 14h8.4",
    "location_on": "M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z M12 10.5v.01",
    "handyman": "M14.5 6.5a3.5 3.5 0 0 0 4.6 4.6L21 13l-8 8-2-2 8-8-1.9-1.9a3.5 3.5 0"
                " 0 0-4.6-4.6L14.5 6.5z M7 3l4 4-4 4-4-4z",
    "bolt": "M13 2 4 14h6l-1 8 9-12h-6l1-8z",
    "verified": "M12 2.5l2.4 2.1 3.2-.3.6 3.1 2.6 1.9-1.5 2.8 1.5 2.8-2.6 1.9-.6 3.1"
                "-3.2-.3L12 21.5l-2.4-2.1-3.2.3-.6-3.1L3.2 14.7l1.5-2.8-1.5-2.8 2.6-1.9"
                ".6-3.1 3.2.3L12 2.5z M8.6 12.2l2.3 2.3 4.5-4.6",
    "shield_lock": "M12 2.8l7 2.6v5.4c0 4.6-2.9 8.6-7 10.4-4.1-1.8-7-5.8-7-10.4V5.4l7-2.6z"
                   " M12 10v-.8a1.6 1.6 0 1 1 3.2 0v.8 M10.4 10h6.4v4.4h-6.4z",
    "query_stats": "M3 20V9 M8.5 20v-6 M14 20v-9 M19.5 20v-4 M3.5 11.5 8.5 7l4.5 3.5L20 4",
    "travel_explore": "M12 21a9 9 0 1 1 6.2-15.5 M3.2 9.8h17.6 M3.2 14.2h9"
                      " M12 3a14 14 0 0 0 0 18 M12 3a14 14 0 0 1 3.6 7"
                      " M17.3 17.3a3.2 3.2 0 1 0 4.5 4.5 3.2 3.2 0 0 0-4.5-4.5z",
    "payments": "M3 7.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z"
                " M10 15.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z M5 4.5h16a2 2 0 0 1 2 2v9",
    "account_tree": "M4 3.5h5v4H4z M15 10.5h5v4h-5z M15 17.5h5v4h-5z"
                    " M6.5 7.5v10.5h6 M6.5 12.5h6",
    "description": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"
                   " M14 3v5h5 M9 13h6 M9 17h6",
    "link": "M10.5 13.5a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 1 0-5.7-5.7L11.6 6.7"
            " M13.5 10.5a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 1 0 5.7 5.7l1.5-1.5",
    "forum": "M7 3h11a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-1v4l-4-4H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"
             " M5 17H4a2 2 0 0 1-2-2V8",
    "check_circle": "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z M8 12.2l2.7 2.7L16 9.6",
    "speed": "M12 20a8 8 0 1 1 8-8 M12 12l4.5-4.5 M4.2 12H2 M22 12h-2.2 M12 4.2V2",
    "key": "M15.5 3a5.5 5.5 0 1 0-4.1 9.2L3 20.6V22h4v-2h2v-2h2l2.4-2.4A5.5 5.5 0 0 0 15.5 3z"
           " M16.8 7.2v.01",
    # Wege in der Seitenleiste
    "dashboard": "M4 4h6v7H4z M14 4h6v4h-6z M14 12h6v8h-6z M4 15h6v5H4z",
    "conversion_path": "M2 12h3.5 M8.5 12h7 M18.5 12H22"
                       " M7 12a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"
                       " M20 12a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"
                       " M12 8.5 15.5 12 12 15.5",
    "checklist": "M9.5 6H21 M9.5 12H21 M9.5 18H21 M3 5.8l1.4 1.4L7 4.6"
                 " M3 11.8l1.4 1.4L7 10.6 M3 17.8l1.4 1.4L7 16.6",
    "account_circle": "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z"
                      " M12 12.5a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"
                      " M5.8 18.6a7 7 0 0 1 12.4 0",
    "passkey": "M9 12.5a4 4 0 1 1 0-8 4 4 0 0 1 0 8z"
               " M2.5 20.5c0-3 2.9-5 6.5-5 1 0 2 .2 2.9.5"
               " M17.5 13.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"
               " M17.5 13.5V19l1.4 1.4-1.4 1.4-1-1",
    # Zustaende und Handlungen
    "error": "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z M12 7.5v5.5 M12 16.5v.01",
    "warning": "M12 3.2 22 20H2L12 3.2z M12 9.5v4.5 M12 17.2v.01",
    "info": "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z M12 11v5.5 M12 7.6v.01",
    "check": "M4.5 12.5l5 5L20 7",
    "close": "M6 6l12 12 M18 6 6 18",
    "add": "M12 5v14 M5 12h14",
    "edit": "M4 20h4L20 8l-4-4L4 16v4z M14.5 5.5l4 4",
    "delete": "M4 6.5h16 M9.5 6.5V4h5v2.5"
              " M6.5 6.5 7.4 20a1 1 0 0 0 1 .9h7.2a1 1 0 0 0 1-.9l.9-13.5"
              " M10 10.5v6.5 M14 10.5v6.5",
    "refresh": "M20 12a8 8 0 1 1-2.3-5.6 M20 4v4.5h-4.5",
    "logout": "M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5 M15 8l4 4-4 4 M19 12H9",
    "arrow_forward": "M5 12h14 M13 6l6 6-6 6",
    "content_copy": "M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1z"
                    " M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
    "visibility": "M12 19c-5 0-8.5-4.2-9.5-7 1-2.8 4.5-7 9.5-7s8.5 4.2 9.5 7c-1 2.8-4.5 7-9.5 7z"
                  " M12 15.2a3.2 3.2 0 1 1 0-6.4 3.2 3.2 0 0 1 0 6.4z",
    # Sachen des Portals
    "person": "M12 12.5a4 4 0 1 1 0-8 4 4 0 0 1 0 8z M4.5 20.5c0-3.6 3.4-6 7.5-6s7.5 2.4 7.5 6",
    "mail": "M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z"
            " M2.4 7.2 12 13.4l9.6-6.2",
    "lock": "M6 10.5h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z"
            " M8.2 10.5V7.8a3.8 3.8 0 0 1 7.6 0v2.7 M12 14.5v2.5",
    "qr_code": "M4 4h5v5H4z M15 4h5v5h-5z M4 15h5v5H4z M15 15h2 M20 15v2 M15 20h5"
               " M12 4v3 M12 10h3 M12 13v4 M12 20h.01 M18 12h2",
    "history": "M3.5 12a8.5 8.5 0 1 0 2.5-6 M3 3v4h4 M12 7.5v5l3.5 2",
    "devices": "M3 5.5h11a1 1 0 0 1 1 1V9 M3 5.5v10h9 M2 18.5h11"
               " M17 9h4a1 1 0 0 1 1 1v8.5a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1z",
    "cloud_done": "M7 19.5a4.5 4.5 0 0 1-.4-9A6 6 0 0 1 18 9.6a4.5 4.5 0 0 1-.5 9H7z"
                  " M9.5 14.5l2 2 4-4",
    "cloud_off": "M18.5 18.5H7a4.5 4.5 0 0 1-1.6-8.7 M9 5.8A6 6 0 0 1 18 9.6a4.5 4.5 0 0 1 3 4.2"
                 " M3 3l18 18",
    "link_off": "M9 15l-2 2a3.6 3.6 0 0 1-5-5l2-2 M15 9l2-2a3.6 3.6 0 0 1 5 5l-2 2 M3 3l18 18",
}


def symbol(name: str, groesse: int = 24, farbe: str = "currentColor") -> str:
    """Ein Symbol als SVG. Unbekannte Namen ergeben nichts, nicht ihren Text."""
    pfad = _PFADE.get(name)
    if not pfad:
        return ""
    return (f'<svg class="sym" width="{groesse}" height="{groesse}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{farbe}" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true" focusable="false">'
            f'<path d="{pfad}"/></svg>')



# --------------------------------------------------------------------------
# Tokens und Grundbausteine, wie das Designsystem sie fuehrt
# --------------------------------------------------------------------------
BASIS_CSS = """
:root{
  --ink-950:#060806; --ink-900:#0B0F0B; --ink-850:#0E130E; --ink-800:#12180F;
  --ink-750:#161D15; --ink-700:#1C241B;
  --line:#232C22; --line-soft:#1A211A; --line-strong:#33402F;
  --fg:#EAF0E9; --fg-soft:#C7D0C6; --muted:#A3ADA3; --faint:#778276;
  --neon:#a8f20d; --neon-up:#bcff33; --neon-dim:#7fb80a; --neon-deep:#3F5A08;
  --violett:#2a025f; --violett-up:#43159A;
  --text-on-accent:#07120A; --text-on-violett:#F2EBFF;
  --warn:#FFB454; --bad:#FF6B5C; --info:#7FD4FF;
  --tint-neon-08:color-mix(in srgb, var(--neon) 8%, transparent);
  --tint-neon-14:color-mix(in srgb, var(--neon) 14%, transparent);
  --tint-warn-14:color-mix(in srgb, var(--warn) 14%, transparent);
  --tint-bad-14:color-mix(in srgb, var(--bad) 14%, transparent);
  --border-accent:color-mix(in srgb, var(--neon) 38%, var(--line));
  --border-hover:color-mix(in srgb, var(--neon) 30%, var(--line));
  --border-bad:color-mix(in srgb, var(--bad) 45%, var(--line));
  --grad-surface:linear-gradient(180deg,#151C14 0%,#11170F 100%);
  --grad-accent:linear-gradient(180deg,#bcff33 0%,#a8f20d 100%);
  --grad-violett:linear-gradient(140deg,#43159A 0%,#2a025f 55%,#150131 100%);
  --grad-hairline:linear-gradient(90deg,transparent,color-mix(in srgb,var(--neon) 35%,transparent),transparent);
  --page-glow:radial-gradient(120% 70% at 50% -10%, color-mix(in srgb,var(--neon) 7%,transparent) 0%, transparent 60%);

  --font-text:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"SF Pro Text",Roboto,"Helvetica Neue",Arial,sans-serif;
  --font-display:"Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,"SF Pro Display",sans-serif;
  --font-mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --text-base:16px;
  --leading-tight:1.14; --leading-heading:1.22; --leading-base:1.62; --leading-note:1.55;
  --size-display-xl:clamp(2.6rem, 1.6rem + 3.4vw, 4.4rem);
  --size-display:clamp(2rem, 1.4rem + 2vw, 3rem);
  --size-h1:2rem; --size-h1-sm:1.5rem; --size-h2:1.18rem; --size-h3:1rem;
  --size-lead:1.06rem; --size-body:1rem; --size-label:.92rem; --size-hint:.85rem;
  --size-note:.875rem; --size-table:.94rem; --size-th:.72rem; --size-state:.78rem;
  --size-mono:.89em; --size-pre:.84rem; --size-eyebrow:.74rem;
  --weight-body:400; --weight-medium:500; --weight-strong:600; --weight-display:680;
  --weight-h1:660; --weight-h2:620; --weight-button:600;
  --tracking-display:-.03em; --tracking-h1:-.022em; --tracking-h2:-.012em;
  --tracking-eyebrow:.14em; --tracking-th:.08em; --tracking-codes:.04em;

  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:20px;
  --space-6:24px; --space-7:32px; --space-8:40px; --space-9:56px; --space-10:72px;
  --radius-xs:6px; --radius-sm:8px; --radius-md:10px; --radius-lg:14px;
  --radius-xl:20px; --radius-pill:999px;
  --control-height:44px; --control-height-sm:34px;
  --measure-app:1080px; --measure-prose:62ch; --measure-narrow:400px;
  --measure-site:1160px; --sidebar-width:248px;

  --shadow-hairline:inset 0 1px 0 rgba(255,255,255,.04);
  --shadow-1:0 1px 2px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.035);
  --shadow-2:0 8px 24px -12px rgba(0,0,0,.75), inset 0 1px 0 rgba(255,255,255,.045);
  --shadow-3:0 24px 60px -24px rgba(0,0,0,.85), inset 0 1px 0 rgba(255,255,255,.05);
  --shadow-inset:inset 0 1px 2px rgba(0,0,0,.5);
  --glow-soft:0 0 0 1px color-mix(in srgb,var(--neon) 30%,transparent), 0 8px 26px -12px color-mix(in srgb,var(--neon) 45%,transparent);
  --glow-accent:0 0 0 1px color-mix(in srgb,var(--neon) 40%,transparent), 0 8px 28px -10px color-mix(in srgb,var(--neon) 45%,transparent);
  --glow-logo:drop-shadow(0 0 20px color-mix(in srgb,var(--neon) 30%,transparent));
  --focus-ring:0 0 0 3px color-mix(in srgb,var(--neon) 26%,transparent);

  --dur-1:120ms; --dur-2:180ms; --dur-3:260ms;
  --ease-out:cubic-bezier(.2,.7,.3,1); --ease-in-out:cubic-bezier(.4,0,.2,1);
  --transition-control:background var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out), box-shadow var(--dur-2) var(--ease-out), transform var(--dur-1) var(--ease-out);
  --transition-surface:background var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
}
@media (prefers-reduced-motion: reduce){
  :root{ --dur-1:0ms; --dur-2:0ms; --dur-3:0ms;
         --transition-control:none; --transition-surface:none; }
}

*{box-sizing:border-box}
html{color-scheme:dark;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ink-900);background-image:var(--page-glow);
  background-repeat:no-repeat;color:var(--fg);
  font:var(--text-base)/var(--leading-base) var(--font-text);
  font-synthesis-weight:none;-webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;text-wrap:pretty}
img,svg{max-width:100%}
::selection{background:color-mix(in srgb,var(--neon) 30%,transparent)}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:var(--radius-pill)}
::-webkit-scrollbar-track{background:transparent}

h1,h2,h3,h4{font-family:var(--font-display);text-wrap:balance;margin:0}
h1{font-size:var(--size-h1);font-weight:var(--weight-h1);
  line-height:var(--leading-heading);letter-spacing:var(--tracking-h1)}
h2{font-size:var(--size-h2);font-weight:var(--weight-h2);line-height:1.3;
  letter-spacing:var(--tracking-h2)}
h3{font-size:var(--size-h3);font-weight:var(--weight-strong);line-height:1.4}
p{margin:0 0 1em} p:last-child{margin-bottom:0}
p.lead{color:var(--muted);font-size:var(--size-lead);max-width:var(--measure-prose);
  margin:var(--space-3) 0 0}
a{color:var(--neon);text-decoration-color:color-mix(in srgb,var(--neon) 45%,transparent);
  text-underline-offset:.22em;transition:color var(--dur-1) var(--ease-out)}
a:hover{color:var(--neon-up);text-decoration-color:currentColor}
hr{border:0;border-top:1px solid var(--line-soft);margin:var(--space-6) 0}
table{width:100%;border-collapse:collapse;font-size:var(--size-table);
  font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:var(--space-3) var(--space-4);vertical-align:top;
  border-bottom:1px solid var(--line-soft)}
th{font-weight:var(--weight-strong);color:var(--faint);font-size:var(--size-th);
  text-transform:uppercase;letter-spacing:var(--tracking-th);white-space:nowrap;
  width:1%;padding-right:var(--space-6)}
tr:last-child th,tr:last-child td{border-bottom:none}
code,.mono,pre,kbd{font-family:var(--font-mono);font-variant-ligatures:none}
code,.mono{font-size:var(--size-mono);color:var(--neon);overflow-wrap:anywhere}
pre{background:var(--ink-850);border:1px solid var(--line);border-radius:var(--radius-md);
  padding:var(--space-4);box-shadow:var(--shadow-inset);overflow-x:auto;
  font-size:var(--size-pre);margin:0;color:var(--fg-soft);white-space:pre-wrap;
  word-break:break-all}

label{display:grid;align-content:start;font-weight:var(--weight-strong);
  font-size:var(--size-label);margin:var(--space-5) 0 0}
label > input,label > select,label > textarea{order:2}
label > span{order:3}
label:first-child{margin-top:0}
.grid-2 > label,.grid-3 > label,.row > label,.stack > label{margin-top:0}
label span{display:block;font-weight:var(--weight-body);color:var(--muted);
  font-size:var(--size-hint);margin-top:var(--space-2);line-height:1.5}
input[type=text],input[type=password],input[type=email],input[type=number],
select,textarea{width:100%;min-height:var(--control-height);padding:0 var(--space-4);
  margin-top:var(--space-2);border:1px solid var(--line);border-radius:var(--radius-md);
  background:var(--ink-850);color:var(--fg);box-shadow:var(--shadow-inset);
  font-family:var(--font-mono);font-size:.92rem;transition:var(--transition-control)}
textarea{padding:var(--space-3) var(--space-4);min-height:120px;line-height:1.55}
input::placeholder,textarea::placeholder{color:var(--faint)}
input:hover,select:hover,textarea:hover{border-color:var(--border-hover)}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--neon);
  box-shadow:var(--focus-ring),var(--shadow-inset)}
input:disabled,select:disabled,textarea:disabled{opacity:.55;cursor:not-allowed}

button,.button{display:inline-flex;align-items:center;justify-content:center;
  gap:var(--space-2);min-height:var(--control-height);padding:0 var(--space-5);
  border-radius:var(--radius-md);border:1px solid transparent;
  background:var(--grad-accent);color:var(--text-on-accent);font:inherit;
  font-weight:var(--weight-button);font-size:.94rem;letter-spacing:-.005em;
  cursor:pointer;text-decoration:none;white-space:nowrap;box-shadow:var(--shadow-1);
  transition:var(--transition-control)}
a.button,a.button:visited{color:var(--text-on-accent);text-decoration:none}
button:hover,.button:hover,a.button:hover{background:var(--neon-up);
  color:var(--text-on-accent);box-shadow:var(--glow-accent)}
button:active,.button:active{background:var(--neon-dim);box-shadow:var(--shadow-1)}
button:focus-visible,.button:focus-visible{outline:2px solid var(--neon-up);outline-offset:2px}
button:disabled,.button[aria-disabled=true]{opacity:.45;cursor:not-allowed;box-shadow:none}
button.quiet,.button.quiet,a.button.quiet{background:var(--ink-750);color:var(--fg);
  border-color:var(--line-strong);box-shadow:var(--shadow-1)}
button.quiet:hover,.button.quiet:hover,a.button.quiet:hover{background:var(--ink-700);
  border-color:var(--neon);color:var(--fg);box-shadow:var(--glow-soft)}
button.quiet:active,.button.quiet:active{background:var(--ink-800);box-shadow:var(--shadow-1)}
button.ghost,.button.ghost,a.button.ghost{background:transparent;color:var(--muted);
  border-color:transparent;box-shadow:none}
button.ghost:hover,.button.ghost:hover,a.button.ghost:hover{background:var(--ink-750);
  color:var(--fg);box-shadow:var(--glow-soft)}
button.danger,.button.danger,a.button.danger{background:transparent;color:var(--bad);
  border-color:color-mix(in srgb,var(--bad) 42%,transparent);box-shadow:none}
button.danger:hover,.button.danger:hover,a.button.danger:hover{background:var(--tint-bad-14);
  color:var(--bad);border-color:var(--bad);
  box-shadow:0 0 0 1px color-mix(in srgb,var(--bad) 35%,transparent),
             0 8px 26px -12px color-mix(in srgb,var(--bad) 55%,transparent)}
button.klein,.button.klein{min-height:var(--control-height-sm);padding:0 var(--space-4);
  font-size:.86rem}
button.breit,.button.breit{width:100%}

.card{position:relative;background:var(--grad-surface);border:1px solid var(--line);
  border-radius:var(--radius-lg);padding:var(--space-6);box-shadow:var(--shadow-2)}
.card + .card{margin-top:var(--space-4)}
.grid-2 > .card + .card,.grid-3 > .card + .card,.stack > .card + .card,
.row > .card + .card{margin-top:0}
.card > h2:first-child{margin-bottom:var(--space-4)}
.card.akzent{border-color:var(--border-accent)}
.card.akzent::before{content:"";position:absolute;inset:0 0 auto;height:1px;
  border-radius:var(--radius-lg) var(--radius-lg) 0 0;background:var(--grad-hairline)}
.card.schlecht{border-color:var(--border-bad)}
.card.flach{box-shadow:var(--shadow-1);background:var(--ink-800)}
.card-kopf{display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)}
.card-kopf h2{margin:0}
.card-kopf .rechts{margin-left:auto;display:flex;gap:var(--space-2);align-items:center}

.eyebrow{display:block;font-size:var(--size-eyebrow);letter-spacing:var(--tracking-eyebrow);
  text-transform:uppercase;color:var(--faint);font-weight:var(--weight-strong)}
.eyebrow.neon{color:var(--neon-dim)}
.state{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;
  padding:3px 10px 3px 8px;border-radius:var(--radius-pill);font-size:var(--size-state);
  font-weight:var(--weight-strong);line-height:1.5;vertical-align:middle;
  font-family:var(--font-text);border:1px solid transparent}
.state::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;
  flex:none;box-shadow:0 0 8px currentColor}
.state.ok{background:var(--tint-neon-14);color:var(--neon);
  border-color:color-mix(in srgb,var(--neon) 22%,transparent)}
.state.warn{background:var(--tint-warn-14);color:var(--warn);
  border-color:color-mix(in srgb,var(--warn) 22%,transparent)}
.state.bad{background:var(--tint-bad-14);color:var(--bad);
  border-color:color-mix(in srgb,var(--bad) 22%,transparent)}
.state.neutral{background:var(--ink-700);color:var(--muted);border-color:var(--line)}
.note{color:var(--muted);font-size:var(--size-note);line-height:var(--leading-note);
  margin:var(--space-3) 0 0;max-width:var(--measure-prose)}
.row{display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:center}
.row.eng{gap:var(--space-2)}
.stack{display:grid;gap:var(--space-4)}
.warnung{display:flex;gap:var(--space-3);padding:var(--space-3) var(--space-4);
  border-radius:var(--radius-md);background:var(--tint-warn-14);
  border:1px solid color-mix(in srgb,var(--warn) 28%,transparent);color:var(--fg);
  font-size:.9rem;line-height:1.55;margin:0 0 var(--space-4)}
.warnung .sym{color:var(--warn);flex:none}
.warnung.schlecht{background:var(--tint-bad-14);
  border-color:color-mix(in srgb,var(--bad) 28%,transparent)}
.warnung.schlecht .sym{color:var(--bad)}
.warnung.gut{background:var(--tint-neon-14);
  border-color:color-mix(in srgb,var(--neon) 28%,transparent)}
.warnung.gut .sym{color:var(--neon)}

label.kasten{display:flex;gap:var(--space-3);align-items:flex-start;margin:0;
  padding:var(--space-3) var(--space-4);border:1px solid var(--line);
  border-radius:var(--radius-md);background:var(--ink-850);font-weight:var(--weight-body);
  cursor:pointer;transition:var(--transition-surface)}
label.kasten + label.kasten{margin-top:var(--space-2)}
label.kasten:hover{border-color:var(--border-hover);background:var(--ink-800)}
label.kasten:has(input:checked){border-color:var(--border-accent);
  background:color-mix(in srgb,var(--neon) 5%,var(--ink-850))}
label.kasten input{accent-color:var(--neon);width:18px;height:18px;margin-top:3px;flex:none}
label.kasten input:disabled{opacity:.5}
.kasten-text{display:block}
.kasten-text b{display:block;font-size:.95rem;font-weight:var(--weight-strong)}
.kasten-text .mono{display:block;color:var(--muted);font-size:.82rem;margin-top:2px}
.kasten-text .note{margin-top:2px}

header.marke{display:flex;align-items:center;gap:var(--space-4)}
header.marke img,header.marke svg{height:26px;width:auto;filter:var(--glow-logo)}
header.marke .wo{margin-left:auto;color:var(--faint);font-size:var(--size-eyebrow);
  letter-spacing:var(--tracking-eyebrow);text-transform:uppercase;
  font-weight:var(--weight-strong)}

nav.nav{display:flex;align-items:center;gap:var(--space-1);flex-wrap:wrap}
nav.nav a{display:inline-flex;align-items:center;gap:var(--space-2);padding:8px 14px;
  border-radius:var(--radius-pill);color:var(--muted);text-decoration:none;
  font-size:.92rem;font-weight:var(--weight-medium);transition:var(--transition-control)}
nav.nav a:hover{color:var(--fg);background:var(--ink-750)}
nav.nav a[aria-current=page]{color:var(--neon);background:var(--tint-neon-08);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--neon) 22%,transparent)}
nav.nav .wer{margin-left:auto;display:flex;align-items:center;gap:var(--space-2);
  color:var(--muted);font-size:.88rem}

ol.schritte{margin:0;padding-left:0;list-style:none;counter-reset:s;display:grid;
  gap:var(--space-3)}
ol.schritte li{counter-increment:s;position:relative;padding-left:34px;font-size:.93rem;
  line-height:1.6;color:var(--fg-soft)}
ol.schritte li::before{content:counter(s);position:absolute;left:0;top:1px;width:22px;
  height:22px;border-radius:50%;display:grid;place-items:center;
  background:var(--tint-neon-14);color:var(--neon);font:600 .72rem/1 var(--font-text)}
ol.codes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2);
  margin:0;padding:0;list-style:none}
ol.codes li{font-family:var(--font-mono);font-size:.95rem;
  letter-spacing:var(--tracking-codes);padding:10px 14px;border-radius:var(--radius-sm);
  background:var(--ink-850);border:1px solid var(--line);color:var(--fg)}

.qr{background:#fff;border-radius:var(--radius-lg);padding:18px 18px 12px;display:flex;
  flex-direction:column;align-items:center;gap:10px;width:fit-content;margin:0;
  box-shadow:var(--shadow-3)}
.qr svg,.qr img{display:block;width:180px;height:auto}
.qr figcaption{color:var(--violett);font-size:.78rem;font-weight:var(--weight-strong);
  letter-spacing:.01em}

.tile{background:var(--ink-800);border:1px solid var(--line);border-radius:var(--radius-md);
  padding:var(--space-4)}
.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:var(--space-4)}
.grid-3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:var(--space-4)}
.grid-2.gleich,.grid-3.gleich{grid-auto-rows:1fr}
.grid-2.gleich > *,.grid-3.gleich > *{height:100%}
.kennzahl{font-family:var(--font-display);font-size:1.7rem;font-weight:var(--weight-display);
  letter-spacing:var(--tracking-h1);line-height:1.1}
.kennzahl.neon{color:var(--neon)}

@media (max-width:640px){
  ol.codes{grid-template-columns:1fr}
  .card{padding:var(--space-5)}
}
"""
