import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { homedir, platform } from 'os';

interface Config {
  file_search_paths?: string[];
  univideo_path?: string;
  [key: string]: any;
}

let cachedConfig: Config | null = null;

/**
 * Find project root by looking for the univa directory
 * This is important for monorepo setups where we need the actual project root,
 * not just the first package.json (which might be in apps/web)
 */
function findProjectRoot(): string {
  let currentDir = process.cwd();
  
  // Keep going up until we find the univa directory or reach root
  while (currentDir !== '/') {
    const univaPath = join(currentDir, 'univa');
    if (existsSync(univaPath)) {
      return currentDir;
    }
    currentDir = dirname(currentDir);
  }
  
  // If not found, return current working directory
  return process.cwd();
}

/**
 * Get the config file path based on the platform
 */
function getConfigPath(): string {
  const appName = 'univa';
  
  if (platform() === 'darwin') {
    // macOS
    return join(homedir(), 'Library', 'Preferences', appName, 'config.toml');
  } else {
    // Linux and others
    return join(homedir(), '.config', appName, 'config.toml');
  }
}

/**
 * Parse TOML config file (simple parser for our needs)
 */
function parseToml(content: string): Config {
  const config: Config = {};
  const lines = content.split('\n');
  
  for (const line of lines) {
    const trimmed = line.trim();
    
    // Skip comments and empty lines
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }
    
    // Parse key = value pairs
    const match = trimmed.match(/^(\w+)\s*=\s*(.+)$/);
    if (match) {
      const [, key, value] = match;
      
      // Handle string values
      if (value.startsWith('"') && value.endsWith('"')) {
        config[key] = value.slice(1, -1);
      }
      // Handle array values (simplified)
      else if (value.startsWith('[') && value.endsWith(']')) {
        const arrayContent = value.slice(1, -1);
        config[key] = arrayContent
          .split(',')
          .map(item => item.trim().replace(/^["']|["']$/g, ''))
          .filter(item => item.length > 0);
      }
      // Handle other values
      else {
        config[key] = value;
      }
    }
  }
  
  return config;
}

/**
 * Load configuration from TOML file
 */
export function loadConfig(): Config {
  if (cachedConfig) {
    return cachedConfig;
  }
  
  const configPath = getConfigPath();
  
  // Find project root dynamically
  const projectRoot = findProjectRoot();
  
  // Default configuration
  const defaultConfig: Config = {
    file_search_paths: [
      join(projectRoot, 'univa'),  // Project root + univa
    ],
  };
  
  // Try to load config file
  if (existsSync(configPath)) {
    try {
      const content = readFileSync(configPath, 'utf-8');
      const config = parseToml(content);
      
      // Merge with defaults
      cachedConfig = { ...defaultConfig, ...config };
    } catch (error) {
      console.warn('Failed to load config file, using defaults:', error);
      cachedConfig = defaultConfig;
    }
  } else {
    cachedConfig = defaultConfig;
  }
  
  return cachedConfig;
}

/**
 * Expand path with home directory
 */
function expandPath(filePath: string): string {
  if (filePath.startsWith('~/')) {
    return join(homedir(), filePath.slice(2));
  }
  return filePath;
}

/**
 * Get file search paths from config
 */
export function getFileSearchPaths(): string[] {
  const config = loadConfig();
  
  // If file_search_paths is configured, use it
  if (config.file_search_paths && Array.isArray(config.file_search_paths)) {
    // Expand paths with ~ and ensure they're absolute
    return config.file_search_paths.map(p => expandPath(p));
  }
  
  // Otherwise, use default: project root + univa
  const projectRoot = findProjectRoot();
  return [join(projectRoot, 'univa')];
}