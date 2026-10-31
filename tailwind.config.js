// Tailwind scans these files for class names and builds only what they use.
// The colors and fonts are the design tokens described in frontend/README.md.
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["frontend/templates/**/*.html", "frontend/static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        towel: "#FAF6F1",
        walnut: "#3A2A22",
        oxblood: { DEFAULT: "#7A1F2B", dark: "#5A1520" },
        mint: { DEFAULT: "#BFE3D5", deep: "#245746" },
        brass: "#B7843A",
        taupe: "#6F625A",
        line: "#E8DFD5",
        steam: "#F1EAE2",
      },
      fontFamily: {
        display: ['"Big Shoulders Display"', "sans-serif"],
        sans: ["Figtree", "system-ui", "sans-serif"],
      },
    },
  },
};
