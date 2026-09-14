import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import {themes as prismThemes} from 'prism-react-renderer';
import fs from 'fs';
import path from 'path';

const plugin = JSON.parse(fs.readFileSync(
  path.join(__dirname, '../plugins/glyphs-mcp/.codex-plugin/plugin.json'), 'utf8'
));
const release = JSON.parse(fs.readFileSync(path.join(__dirname, '../release.json'), 'utf8'));
const gmcpVersion: string = plugin.version + (release.channel === 'beta' ? ` Beta ${release.betaNumber}` : '');

const config: Config = {
  title: 'Glyphs MCP',
  tagline: 'A Model Context Protocol server for Glyphs that exposes font-specific tools to AI and LLM agents.',
  favicon: 'img/favicon.svg',

  url: 'https://thierryc.github.io',
  baseUrl: '/Glyphs-mcp/',

  organizationName: 'thierryc',
  projectName: 'Glyphs-mcp',

  onBrokenLinks: 'throw',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'throw'
    }
  },

  customFields: {
    gmcpVersion,
    legacyVersion: '1.11.0'
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
          // Keep existing released v1 URLs; v2 has its own explicit route.
          lastVersion: 'current',
          versions: {
            current: {label: `v2 · ${gmcpVersion}`, path: 'v2', banner: 'none'},
            '1.11.0': {label: 'v1 · 1.11.0', path: '', banner: 'none'}
          }
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
        {type: 'docsVersionDropdown', position: 'left'},
        {
          href: 'https://github.com/thierryc/Glyphs-mcp/releases',
          label: 'Releases',
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
            {label: 'v2 · Glyphs 4', to: '/docs/v2/'},
            {label: 'v1 · 1.11.0', to: '/docs/'},
            {label: 'Moving from v1 to v2', to: '/docs/v2/getting-started/migrate-from-v1'}
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
