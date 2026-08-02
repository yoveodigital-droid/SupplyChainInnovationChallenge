/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm paper and deep ink: deliberately not default-Tailwind grey.
        paper: { DEFAULT: "#F7F4EE", raised: "#FFFDF8", sunken: "#EFEAE1" },
        ink: { DEFAULT: "#17181D", soft: "#4A4C57", faint: "#8A8C99" },
        line: { DEFAULT: "#E2DCD1", strong: "#CFC7B8" },
        // One strong accent, chosen to stay clearly distinct from the
        // green/amber/red risk triad.
        accent: {
          DEFAULT: "#5B2BD9",
          soft: "#EDE7FD",
          mid: "#8B6BF0",
          deep: "#3A1699",
        },
        risk: {
          green: "#0F8A54",
          greenSoft: "#DCF3E7",
          amber: "#B87400",
          amberSoft: "#FCEFD5",
          red: "#C42A2A",
          redSoft: "#FBE3E1",
        },
        sea: { DEFAULT: "#DCE6EC", deep: "#C3D3DD", land: "#EAE4D8" },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(23,24,29,0.04), 0 8px 24px -12px rgba(23,24,29,0.18)",
        lift: "0 2px 4px rgba(23,24,29,0.06), 0 18px 40px -16px rgba(23,24,29,0.30)",
        phone: "0 30px 70px -20px rgba(23,24,29,0.45)",
      },
      borderRadius: { xl2: "1.25rem", phone: "2.6rem" },
      keyframes: {
        "bubble-in": {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.85)", opacity: "0.7" },
          "70%": { transform: "scale(1.9)", opacity: "0" },
          "100%": { transform: "scale(1.9)", opacity: "0" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "bubble-in": "bubble-in 320ms cubic-bezier(0.22,1,0.36,1) both",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4,0,0.6,1) infinite",
      },
    },
  },
  plugins: [],
};
