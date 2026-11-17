import fs from "node:fs";
import { createRequire } from "node:module";
import type { NextConfig } from "next";

const require = createRequire(import.meta.url);

function canonicalizeCommonjsResult(result: unknown, searchRoot: string): unknown {
  if (typeof result !== "string" || !result.startsWith("commonjs ")) {
    return result;
  }
  const target = result.slice("commonjs ".length);
  if (
    target === "react" ||
    target.startsWith("react/") ||
    target === "react-dom" ||
    target.startsWith("react-dom/") ||
    target.startsWith("next/")
  ) {
    try {
      const realPath = fs.realpathSync.native(require.resolve(target, { paths: [searchRoot] }));
      return `commonjs ${realPath}`;
    } catch {
      return result;
    }
  }
  return result;
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
  webpack(config, { isServer }) {
    const rawContext = typeof config.context === "string" ? config.context : process.cwd();
    const realContext = fs.realpathSync.native(rawContext);
    if (realContext !== rawContext) {
      config.context = realContext;
    }

    // On Windows, if a shell launches `next build` with mismatched directory casing
    // (e.g. lowercase folder vs NTFS casing), canonicalize externalized React/Next shared
    // runtime targets to the real filesystem path so Node loads a single shared instance.
    if (isServer && process.platform === "win32" && realContext !== rawContext && config.externals) {
      const prevExternals = Array.isArray(config.externals)
        ? config.externals
        : [config.externals];

      config.externals = prevExternals.map((entry: unknown) => {
        if (typeof entry !== "function") {
          return entry;
        }
        return (
          data: unknown,
          callback: (err?: Error | null, result?: unknown, type?: string) => void,
        ) => {
          const maybePromise = (entry as (d: unknown, cb?: unknown) => unknown)(
            data,
            (err?: Error | null, result?: unknown, type?: string) => {
              if (err) {
                callback(err);
                return;
              }
              callback(null, canonicalizeCommonjsResult(result, realContext), type);
            },
          );
          if (maybePromise && typeof (maybePromise as Promise<unknown>).then === "function") {
            return (maybePromise as Promise<unknown>).then((res) =>
              canonicalizeCommonjsResult(res, realContext),
            );
          }
          return maybePromise;
        };
      });
    }

    return config;
  },
};

export default nextConfig;
