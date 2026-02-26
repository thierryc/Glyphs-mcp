import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import {themes as prismThemes} from 'prism-react-renderer';
import fs from 'fs';
import path from 'path';

function readGlyphsMcpVersion(): string {
  try {
    const infoPlistPath = path.join(
      __dirname,
      '..',
      'src',
      'glyphs-mcp',
      'Glyphs MCP.glyphsPlugin',
      'Contents',
      'Info.plist'
    );
    const contents = fs.readFileSync(infoPlistPath, 'utf8');
    const match = contents.match(
      /<key>CFBundleShortVersionString<\/key>\s*<string>([^<]+)<\/string>/
    );
    return match?.[1]?.trim() || 'dev';
  } catch {
    return 'dev';
  }
}

const gmcpVersion = readGlyphsMcpVersion();

const config: Config = {
  title: 'Glyphs MCP',
  tagline: 'A Model Context Protocol server for Glyphs that exposes font-specific tools to AI and LLM agents.',
  favicon: 'img/favicon.svg',

  url: 'https://thierryc.github.io',
  baseUrl: '/Glyphs-mcp/',

  organizationName: 'thierryc',
  projectName: 'Glyphs-mcp',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  customFields: {
    gmcpVersion
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en']
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../content',
          routeBasePath: 'docs',
          sidebarPath: require.resolve('./sidebars.ts'),
          editUrl: 'https://github.com/thierryc/Glyphs-mcp/tree/main/'
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css')
        }
      } satisfies Preset.Options
    ]
  ],

  themeConfig: {
    navbar: {
      title: 'Glyphs MCP',
      logo: {
        alt: 'Glyphs MCP',
        src: 'img/logo.svg'
      },
      items: [
        {type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs'},
        {
          href: 'https://github.com/thierryc/Glyphs-mcp/releases',
          label: `v${gmcpVersion}`,
          position: 'right'
        },
        {
          href: 'https://github.com/thierryc/Glyphs-mcp',
          label: 'GitHub',
          position: 'right'
        }
      ]
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Getting Started', to: '/docs/getting-started/installation'},
            {label: 'Guides', to: '/docs/kerning-workflow'}
          ]
        },
        {
          title: 'Community',
          items: [{label: 'Glyphs Forum', href: 'https://forum.glyphsapp.com/'}]
        },
        {
          title: 'More',
          items: [
            {label: 'GitHub', href: 'https://github.com/thierryc/Glyphs-mcp'},
            {label: 'License', href: 'https://github.com/thierryc/Glyphs-mcp/blob/main/LICENSE'}
          ]
        }
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Glyphs MCP contributors.`
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula
    }
  } satisfies Preset.ThemeConfig
};

export default config;
