/** @type {import('tailwindcss').Config} */
// Farben kommen aus CSS-Variablen (src/index.css), damit Hell/Dunkel an einer Stelle umschaltet.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        page: v("page"),
        surface: v("surface"),
        raised: v("raised"),
        ink: v("ink"),
        ink2: v("ink2"),
        muted: v("muted"),
        line: v("line"),
        accent: v("s1"),
        good: v("good"),
        bad: v("bad"),
      },
      fontFamily: { sans: ['system-ui', '-apple-system', '"Segoe UI"', "sans-serif"] },
      borderRadius: { xl2: "1.25rem" },
      boxShadow: {
        card: "0 1px 2px rgb(0 0 0 / 0.04), 0 8px 24px -12px rgb(0 0 0 / 0.12)",
      },
    },
  },
  plugins: [],
};
