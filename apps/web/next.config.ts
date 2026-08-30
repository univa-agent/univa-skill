import type { NextConfig } from "next";
import path from "node:path";
import { withBotId } from "botid/next/config";

const appRoot = process.cwd();
const repoRoot = path.resolve(appRoot, "../..");
const appNodeModules = path.join(appRoot, "node_modules");
const repoNodeModules = path.join(repoRoot, "node_modules");
const appBunNodeModules = path.join(appNodeModules, ".bun", "node_modules");
const repoBunNodeModules = path.join(repoNodeModules, ".bun", "node_modules");
const repoParent = path.dirname(repoRoot);
const repoGrandParent = path.dirname(repoParent);

const isInsideRepo = (candidate: string) => {
  const relativePath = path.relative(repoRoot, candidate);

  return (
    relativePath === "" ||
    (!relativePath.startsWith("..") && !path.isAbsolute(relativePath))
  );
};

const unique = <T>(items: T[]) => Array.from(new Set(items));

const projectResolveModules = (modules: string[] = []) =>
  unique([
    appNodeModules,
    repoNodeModules,
    appBunNodeModules,
    repoBunNodeModules,
    ...modules.filter(
      (modulePath) => path.isAbsolute(modulePath) && isInsideRepo(modulePath)
    ),
  ]);

const nextConfig: NextConfig = {
  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
  reactStrictMode: true,
  productionBrowserSourceMaps: true,
  output: "standalone",
  watchOptions: {
    pollIntervalMs: 1000,
  },
  webpack: (config) => {
    config.resolve = config.resolve ?? {};
    config.resolve.modules = projectResolveModules(config.resolve.modules);

    config.resolveLoader = config.resolveLoader ?? {};
    config.resolveLoader.modules = projectResolveModules(
      config.resolveLoader.modules
    );

    config.watchOptions = {
      ...config.watchOptions,
      poll: 1000,
      ignored: [
        repoParent,
        repoGrandParent,
        "**/node_modules/**",
        "**/.next/**",
        "**/.git/**",
        "**/__pycache__/**",
      ],
      aggregateTimeout: 300,
    };
    return config;
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "plus.unsplash.com",
      },
      {
        protocol: "https",
        hostname: "images.unsplash.com",
      },
      {
        protocol: "https",
        hostname: "images.marblecms.com",
      },
      {
        protocol: "https",
        hostname: "lh3.googleusercontent.com",
      },
      {
        protocol: "https",
        hostname: "avatars.githubusercontent.com",
      },
    ],
  },
};

export default withBotId(nextConfig);
