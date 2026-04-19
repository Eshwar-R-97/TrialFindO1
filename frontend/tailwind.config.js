/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-alt": "hsl(var(--card-alt))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        brand: {
          50:  "#f0fbf7",
          100: "#d1f4e8",
          200: "#a3e8d1",
          300: "#6dd4b5",
          400: "#3dbb96",
          500: "#1D9E75",
          600: "#188964",
          700: "#136f50",
          800: "#0f5640",
          900: "#0b3f30",
          950: "#051f18",
        },
        surface: {
          950: "#020c07",
          900: "#040f09",
          800: "#071a0f",
          700: "#0c2818",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(15, 23, 42, 0.04)",
        card: "0 4px 16px rgba(15, 23, 42, 0.06)",
        lift: "0 10px 30px rgba(15, 23, 42, 0.08)",
        "glow-brand": "0 0 30px rgba(29, 158, 117, 0.4)",
        "glow-brand-lg": "0 0 60px rgba(29, 158, 117, 0.5)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseRing: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(29, 158, 117, 0.5)" },
          "50%": { boxShadow: "0 0 0 8px rgba(29, 158, 117, 0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-18px)" },
        },
        floatAlt: {
          "0%, 100%": { transform: "translateY(0px) translateX(0px)" },
          "33%": { transform: "translateY(-12px) translateX(8px)" },
          "66%": { transform: "translateY(-6px) translateX(-6px)" },
        },
        gradientShift: {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        slideUpFade: {
          from: { opacity: "0", transform: "translateY(20px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          from: { opacity: "0", transform: "scale(0.94)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "pulse-ring": "pulseRing 1.3s ease-in-out infinite",
        shimmer: "shimmer 1.8s ease-in-out infinite",
        float: "float 7s ease-in-out infinite",
        "float-alt": "floatAlt 9s ease-in-out infinite",
        "gradient-shift": "gradientShift 5s ease infinite",
        "slide-up-fade": "slideUpFade 0.5s ease-out forwards",
        "scale-in": "scaleIn 0.4s ease-out forwards",
      },
    },
  },
  plugins: [],
};
