import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'glyphs-mcp',
    {
      type: 'category',
      label: 'Concepts',
      items: ['concepts/how-glyphs-mcp-works', 'concepts/safety-model']
    },
    {
      type: 'category',
      label: 'Tutorial',
      items: ['tutorial/first-session']
    },
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/installation',
        'getting-started/start-server',
        'getting-started/connect-client',
        'getting-started/troubleshooting'
      ]
    },
    {
      type: 'category',
      label: 'Guides',
      items: ['kerning-workflow', 'kerning-tools', 'spacing-tools']
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['reference/command-set', 'reference/resources']
    }
  ]
};

export default sidebars;
