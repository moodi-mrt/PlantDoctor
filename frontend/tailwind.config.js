/** Design tokens — PlantDoctor. Forest/emerald on warm off-white; one accent, restrained. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        forest: { 50: "#F1F7F3", 100: "#DDEDE2", 200: "#BCDAC6", 300: "#8EC0A1", 400: "#5C9E77", 500: "#3A8059", 600: "#256544", 700: "#1B5236", 800: "#14532D", 900: "#0F3D22", 950: "#08241380" },
        emerald: { 50: "#ECFDF5", 100: "#D1FAE5", 500: "#10B981", 600: "#059669", 700: "#047857" },
        paper: { DEFAULT: "#FAFAF7", 2: "#F4F3EE", 3: "#ECEAE3" },
        ink: { DEFAULT: "#18211B", 2: "#3E4A42", 3: "#5B6760", 4: "#626D66" },  // 3 and 4 meet WCAG AA (>=4.5:1) on paper backgrounds
        line: { DEFAULT: "#E4E6E0", strong: "#CDD2CA" },
        warn: { 50: "#FFF8EB", 100: "#FEEBC8", 600: "#B45309", 700: "#92400E" },
        bad: { 50: "#FEF3F2", 100: "#FEE4E2", 600: "#C4320A", 700: "#9A2A0A" },
        info: { 50: "#EFF6FF", 600: "#1D4ED8" },
      },
      fontFamily: { sans: ['"Inter Variable"', "Inter", "system-ui", "sans-serif"] },
      borderRadius: { xl: "14px", "2xl": "18px" },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,20,.04), 0 1px 1px rgba(16,24,20,.03)",
        lift: "0 8px 24px -8px rgba(16,40,26,.16), 0 2px 6px rgba(16,24,20,.05)",
      },
      fontSize: { "2xs": ["11px", "14px"] },
      maxWidth: { page: "1200px" },
    },
  },
  plugins: [],
};
