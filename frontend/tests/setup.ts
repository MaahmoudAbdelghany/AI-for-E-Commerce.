import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

function resetTestEnvironment() {
  if (typeof window !== "undefined") {
    try {
      window.localStorage?.clear();
    } catch {
      // Ignore storage access errors in SSR-mocked unit tests.
    }
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = "ar";
    document.documentElement.dir = "rtl";
  }
}

beforeEach(() => {
  resetTestEnvironment();
});

afterEach(() => {
  cleanup();
  resetTestEnvironment();
});
