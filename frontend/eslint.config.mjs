import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nextPlugin = require("@next/eslint-plugin-next");
const tsPlugin = require("@typescript-eslint/eslint-plugin");
const reactPlugin = require("eslint-plugin-react");
const reactHooksPlugin = require("eslint-plugin-react-hooks");
const jsxA11yPlugin = require("eslint-plugin-jsx-a11y");

const eslintConfig = [
  {
    ignores: [".next/**", "out/**", "node_modules/**", "coverage/**", "next-env.d.ts"],
  },
  reactPlugin.configs.flat.recommended,
  reactPlugin.configs.flat["jsx-runtime"],
  reactHooksPlugin.configs["recommended-latest"],
  jsxA11yPlugin.flatConfigs.recommended,
  ...tsPlugin.configs["flat/recommended"],
  nextPlugin.flatConfig.coreWebVitals,
  {
    settings: {
      react: {
        version: "detect",
      },
    },
    rules: {
      "react/prop-types": "off",
      // Feature 3.2 OfferCard intentionally renders raw <img> tags with strict https:// validation
      // and referrerPolicy="no-referrer" instead of routing external marketplace CDNs via next/image.
      "@next/next/no-img-element": "off",
    },
  },
];

export default eslintConfig;
