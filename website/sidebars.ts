import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    {
      type: 'category',
      label: 'Overview',
      items: ['glyphs-mcp']
    },
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/installation',
        'tutorial/first-session',
        'getting-started/start-server',
        'getting-started/connect-client',
        'getting-started/use-agent-skills',
        'getting-started/troubleshooting'
      ]
    },
    {
      type: 'category',
      label: 'Concepts',
      items: ['concepts/how-glyphs-mcp-works', 'concepts/agent-skills', 'concepts/safety-model']
    },
    {
      type: 'category',
      label: 'Workflows',
      items: [
        'kerning-workflow',
        'kerning-tools',
        'spacing-tools',
        'compensated-tuning-tools',
        'workflows/style-set-inspection',
        'workflows/outlines-selected-nodes',
        'workflows/export-designspace-ufo'
      ]
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['reference/command-set', 'reference/settings', 'reference/resources']
    },
    {
      type: 'category',
      label: 'Contributor Notes',
      items: ['contributor/local-docs-development', 'contributor/release-build-notes']
    }
  ]
};

export default sidebars;
