# SQLNav Theme & Color Customization Guide

This guide explains how theme switching works in SQLNav and how you can easily customize or add colors for **Light Mode** and **Dark Mode**.

---

## 🎨 Where to Change Colors

The central color palette file is:
👉 **[`frontend/app/theme-colors.css`](file:///home/nitish/Desktop/AI-Database-Navigator/frontend/app/theme-colors.css)**

All colors used throughout the frontend are defined in this single file. Any edits saved here hot-reload immediately in your browser!

---

## 🖌️ Color Token Reference

Colors are written in **HSL format** (`<hue> <saturation>% <lightness>%`) without the `hsl()` wrapper.

| Variable Name | Purpose & Where It's Used | Example Light | Example Dark |
|---|---|---|---|
| `--background` | Main page canvas background | `210 25% 98%` (#f8fafc) | `0 0% 5%` (#0d0d0d) |
| `--background_alt` | Panels, cards, sidebars, query input area | `0 0% 100%` (#ffffff) | `0 0% 7%` (#121212) |
| `--foreground` | Subtle borders, card outlines, table dividers | `214 32% 88%` (#cbd5e1) | `0 0% 18%` (#2e2e2e) |
| `--foreground_alt` | Hover backgrounds for buttons, active items | `210 20% 93%` (#f1f5f9) | `0 0% 20%` (#333333) |
| `--primary` | Main text, titles, headings, and active labels | `222 47% 11%` (#0f172a) | `0 0% 95%` (#f2f2f2) |
| `--secondary` | Muted text, subtitles, icons, timestamps | `215 16% 47%` (#64748b) | `0 0% 50%` (#808080) |
| `--muted-foreground` | Placeholder text, subtle hints, captions | `215 16% 47%` (#64748b) | `0 0% 45.1%` (#737373) |
| `--accent` | SQLNav brand emerald accent (buttons, active pills) | `151 60% 36%` (#15803d) | `151 46% 51%` (#47c385) |
| `--accent-foreground` | High-contrast text on accent badges | `151 80% 20%` (#052e16) | `134 80% 32%` (#10b981) |
| `--background_accent` | Soft green pastel wash for demo/active badges | `151 55% 94%` (#ecfdf5) | `151 52% 28%` (#14532d) |
| `--highlight` | Sky blue for source code icons, links, info | `202 85% 42%` (#0284c7) | `202 54% 59%` (#5dade2) |
| `--warning` | Amber warning status indicators | `28 85% 44%` (#d97706) | `18 72% 49%` (#e06d1a) |
| `--error` | Crimson error indicators and delete buttons | `353 75% 50%` (#dc2626) | `353 49% 44%` (#a7384a) |
| `--background_error` | Soft red background tint for error alerts | `353 80% 96%` (#fef2f2) | `340 52% 25%` (#4c0519) |

---

## 💡 Quick Cheat Sheet: Hex to HSL

You can easily convert your favorite hex color codes to HSL:

| Hex Color | Color Description | HSL Value to Put in `theme-colors.css` |
|---|---|---|
| `#ffffff` | Pure White | `0 0% 100%` |
| `#000000` | Pure Black | `0 0% 0%` |
| `#f8fafc` | Slate 50 (Soft Canvas) | `210 40% 98%` |
| `#f1f5f9` | Slate 100 (Hover Surface) | `210 40% 96%` |
| `#e2e8f0` | Slate 200 (Subtle Border) | `214 32% 91%` |
| `#cbd5e1` | Slate 300 (Crisp Border) | `214 32% 88%` |
| `#64748b` | Slate 500 (Muted Text) | `215 16% 47%` |
| `#0f172a` | Slate 900 (Rich Dark Text) | `222 47% 11%` |
| `#10b981` | Vibrant Emerald | `151 55% 42%` |
| `#059669` | Deep Emerald (Light Mode) | `151 60% 36%` |
| `#0ea5e9` | Sky Blue | `202 85% 48%` |
| `#3b82f6` | Royal Blue | `217 91% 60%` |
| `#8b5cf6` | Violet Purple | `258 90% 66%` |
| `#ef4444` | Red 500 | `353 75% 50%` |

---

## 🔘 Theme Toggle Button

The theme toggle button is available in multiple locations:

1. **Sidebar Footer**: Located right next to the logout button for easy access anytime.
2. **Login & Onboarding Pages**: Floating pill toggle at the top-right corner (`top-4 right-4`).
3. **Settings Page**: Full "Appearance" section with a segmented control (`Light` / `Dark` / `System`).

### Using the Toggle in Code
You can drop the `<ThemeToggle />` component into any component:
```tsx
import ThemeToggle from "@/app/components/shared/ThemeToggle";

// Icon button (compact)
<ThemeToggle variant="icon" size="sm" />

// Sliding pill toggle
<ThemeToggle variant="pill" />

// Segmented (Light / Dark / System)
<ThemeToggle variant="segmented" />
```

Or consume the `useTheme()` hook:
```tsx
import { useTheme } from "@/app/components/contexts/ThemeContext";

const { theme, resolvedTheme, toggleTheme, setTheme } = useTheme();
```
